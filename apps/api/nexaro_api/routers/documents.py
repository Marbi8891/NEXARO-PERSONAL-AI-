"""Documentos de una organización: carga de texto, búsqueda y preguntas con fuentes (ADR-0012)."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ai_gateway.errors import PolicyError, ProviderError
from ai_gateway.schemas import ChatMessage, CompletionRequest
from nexaro_api.deps import (
    Ctx,
    OrgAccess,
    acquire_generation,
    client_ip,
    require_permission,
    validate_origin,
)
from nexaro_api.schemas import DocumentAskRequest, DocumentCreateRequest
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from products.personal_ai import documents as docs
from products.personal_ai import pdf
from products.personal_ai.prompts import build_system_prompt

router = APIRouter(prefix="/api/organizations/{organization_id}/documents", tags=["documents"])

CanRead = Annotated[OrgAccess, Depends(require_permission("documents:read"))]
CanWrite = Annotated[OrgAccess, Depends(require_permission("documents:write"))]
TOP_FRAGMENTS = 4
NO_ANSWER = "No he encontrado información sobre eso en los documentos de la organización."
_ERRORS = {
    docs.EmptyDocumentError: 422,
    docs.DocumentTooLargeError: 413,
    docs.DocumentLimitError: 409,
    docs.DuplicateDocumentError: 409,
    pdf.InvalidPdfError: 422,
    pdf.EncryptedPdfError: 422,
    pdf.NoTextError: 422,
    pdf.TooManyPagesError: 413,
}


def _hit(h: docs.Hit) -> dict[str, Any]:
    return {
        "document_id": h.document_id,
        "title": h.title,
        "ordinal": h.ordinal,
        "snippet": h.snippet,
        "score": h.score,
    }


@router.get("")
def list_all(organization_id: str, access: CanRead, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {
            "documents": docs.list_documents(db, organization_id),
            "limits": {"max_chars": docs.MAX_CHARS, "max_documents": docs.MAX_DOCUMENTS},
        }


def _store(
    ctx: Ctx,
    request: Request,
    access: OrgAccess,
    organization_id: str,
    *,
    title: str,
    content: str,
    source: str | None,
    mime_type: str | None,
) -> dict[str, Any]:
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            created = docs.create_document(
                db,
                organization_id,
                access.user["id"],
                title,
                content,
                source=source,
                mime_type=mime_type,
            )
        except docs.DocumentError as exc:
            raise HTTPException(status_code=_ERRORS[type(exc)], detail=str(exc)) from exc
        record_event(
            db,
            "document.create",
            "success",
            actor_user_id=access.user["id"],
            target_type="document",
            target_id=created["id"],
            ip=client_ip(request),
            details={"organization": organization_id, "chunks": created["chunk_count"]},
        )
    return created


@router.post("", status_code=201)
def create(
    organization_id: str,
    body: DocumentCreateRequest,
    request: Request,
    access: CanWrite,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    return _store(
        ctx,
        request,
        access,
        organization_id,
        title=body.title.strip(),
        content=body.content,
        source=body.source,
        mime_type=body.mime_type,
    )


@router.post("/pdf", status_code=201)
async def create_from_pdf(
    organization_id: str,
    request: Request,
    access: CanWrite,
    ctx: Ctx,
    title: Annotated[str, Query(min_length=1, max_length=200)],
    source: Annotated[str | None, Query(max_length=255)] = None,
) -> dict[str, Any]:
    """PDF con texto como cuerpo binario crudo (`Content-Type: application/pdf`). El tamaño lo
    limita `MAX_BODY_BYTES`; la extracción corre en un hilo para no bloquear el servidor."""
    validate_origin(request, ctx)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/pdf":
        raise HTTPException(status_code=415, detail="Se esperaba un PDF (application/pdf)")
    if not title.strip():
        raise HTTPException(status_code=422, detail="El título no puede estar vacío")
    data = await request.body()
    try:
        text = await asyncio.to_thread(pdf.extract_text, data)
    except docs.DocumentError as exc:
        raise HTTPException(status_code=_ERRORS[type(exc)], detail=str(exc)) from exc
    return await asyncio.to_thread(
        _store,
        ctx,
        request,
        access,
        organization_id,
        title=title.strip(),
        content=text,
        source=source,
        mime_type="application/pdf",
    )


@router.delete("/{document_id}", status_code=204)
def delete(
    organization_id: str, document_id: str, request: Request, access: CanWrite, ctx: Ctx
) -> None:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        if not docs.delete_document(db, organization_id, document_id):
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        record_event(
            db,
            "document.delete",
            "success",
            actor_user_id=access.user["id"],
            target_type="document",
            target_id=document_id,
            ip=client_ip(request),
            details={"organization": organization_id},
        )


@router.get("/search")
def search(
    organization_id: str, access: CanRead, ctx: Ctx, q: str, limit: int = 5
) -> dict[str, Any]:
    if not q.strip() or len(q) > 500:
        raise HTTPException(status_code=422, detail="Consulta no válida")
    with ctx.database.connect() as db:
        hits = docs.search(db, organization_id, q, min(max(limit, 1), 20))
    return {"results": [_hit(h) for h in hits]}


@router.post("/ask")
async def ask(
    organization_id: str,
    body: DocumentAskRequest,
    request: Request,
    access: CanRead,
    ctx: Ctx,
) -> dict[str, Any]:
    """Responde con los fragmentos más relevantes como contexto. Sin fragmentos relevantes no se
    consulta al modelo: se dice que no hay información (evita respuestas inventadas)."""
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        hits = docs.search(db, organization_id, body.question, TOP_FRAGMENTS)
    if not hits:
        return {"answer": NO_ANSWER, "sources": []}

    system = build_system_prompt(
        provider=ctx.provider.name.capitalize(), model=ctx.personal_ai.model
    )
    system += docs.DOCUMENT_RULES
    user = f"{docs.build_context(hits)}\n\nPregunta: {body.question}"
    lease = acquire_generation(ctx, f"user:{access.user['id']}")
    try:
        result = await ctx.provider.complete(
            CompletionRequest(
                model=ctx.personal_ai.model,
                messages=[
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ],
                user_id=access.user["id"],
                organization_id=organization_id,
            )
        )
    except PolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail="Error al consultar el servicio de IA") from exc
    finally:
        lease.release()
    return {"answer": result.content, "sources": [_hit(h) for h in hits]}
