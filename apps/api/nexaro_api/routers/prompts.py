"""Biblioteca de prompts por organización y catálogo de solo lectura (ADR-0023)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from nexaro_api.deps import (
    Ctx,
    CurrentUser,
    OrgAccess,
    client_ip,
    require_permission,
    validate_origin,
)
from nexaro_api.schemas import (
    ChatRequest,
    PromptCreateRequest,
    PromptInstallRequest,
    PromptRenderRequest,
    PromptUpdateRequest,
)
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from products.personal_ai import prompt_library as svc

router = APIRouter(prefix="/api/organizations/{organization_id}/prompts", tags=["prompts"])
catalogue_router = APIRouter(prefix="/api/prompt-catalogue", tags=["prompts"])

CanRead = Annotated[OrgAccess, Depends(require_permission("prompts:read"))]
CanWrite = Annotated[OrgAccess, Depends(require_permission("prompts:write"))]
NOT_FOUND = HTTPException(status_code=404, detail="Prompt no encontrado")
CHAT_MAX_CHARS: int = next(
    m.max_length for m in ChatRequest.model_fields["message"].metadata if hasattr(m, "max_length")
)


def _invalid(exc: svc.PromptError) -> HTTPException:
    if isinstance(exc, svc.MissingVariablesError):
        return HTTPException(status_code=422, detail={"missing_variables": exc.missing})
    return HTTPException(status_code=422, detail=str(exc))


def _audit(
    db: Any, action: str, access: OrgAccess, request: Request, target: str, org: str, **extra: Any
) -> None:
    record_event(
        db,
        action,
        "success",
        actor_user_id=access.user["id"],
        target_type="prompt",
        target_id=target,
        ip=client_ip(request),
        details={"organization": org, **extra},
    )


@catalogue_router.get("")
def list_catalogue(user: CurrentUser, category: str | None = None) -> dict[str, Any]:
    items = [p for p in svc.catalogue() if category is None or p["category"] == category]
    return {
        "total": len(items),
        "items": items,
        "categories": sorted({p["category"] for p in svc.catalogue()}),
    }


@router.get("")
def list_all(
    organization_id: str,
    access: CanRead,
    ctx: Ctx,
    q: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        with ctx.database.connect() as db:
            return svc.list_prompts(
                db, organization_id, query=q, category=category, tag=tag, limit=limit, offset=offset
            )
    except svc.PromptError as exc:
        raise _invalid(exc) from exc


@router.post("", status_code=201)
def create(
    organization_id: str, body: PromptCreateRequest, request: Request, access: CanWrite, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            created = svc.create_prompt(db, organization_id, access.user["id"], body.model_dump())
        except svc.PromptError as exc:
            raise _invalid(exc) from exc
        _audit(db, "prompt.create", access, request, created["id"], organization_id)
    return created


@router.post("/install", status_code=201)
def install(
    organization_id: str, body: PromptInstallRequest, request: Request, access: CanWrite, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            result = svc.install_from_catalogue(
                db, organization_id, access.user["id"], body.catalogue_id
            )
        except svc.PromptError as exc:
            raise _invalid(exc) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="No existe en el catálogo")
        prompt, created = result
        if created:
            _audit(
                db,
                "prompt.install",
                access,
                request,
                prompt["id"],
                organization_id,
                catalogue_id=body.catalogue_id,
            )
    return {**prompt, "installed_now": created}


@router.get("/{prompt_id}")
def get_one(organization_id: str, prompt_id: str, access: CanRead, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        prompt = svc.get_prompt(db, organization_id, prompt_id)
    if prompt is None:
        raise NOT_FOUND
    return prompt


@router.patch("/{prompt_id}")
def update(
    organization_id: str,
    prompt_id: str,
    body: PromptUpdateRequest,
    request: Request,
    access: CanWrite,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    changes = body.model_dump(exclude_unset=True, exclude={"changelog"})
    if not changes or any(v is None for v in changes.values()):
        raise HTTPException(status_code=422, detail="Indica al menos un campo válido")
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            updated = svc.update_prompt(
                db, organization_id, prompt_id, access.user["id"], changes, body.changelog
            )
        except svc.PromptError as exc:
            raise _invalid(exc) from exc
        if updated is None:
            raise NOT_FOUND
        _audit(
            db, "prompt.update", access, request, prompt_id, organization_id, fields=sorted(changes)
        )
    return updated


@router.delete("/{prompt_id}", status_code=204)
def delete(
    organization_id: str, prompt_id: str, request: Request, access: CanWrite, ctx: Ctx
) -> None:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        if not svc.delete_prompt(db, organization_id, prompt_id):
            raise NOT_FOUND
        _audit(db, "prompt.delete", access, request, prompt_id, organization_id)


@router.get("/{prompt_id}/versions")
def versions(organization_id: str, prompt_id: str, access: CanRead, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        items = svc.list_versions(db, organization_id, prompt_id)
    if items is None:
        raise NOT_FOUND
    return {"items": items}


@router.post("/{prompt_id}/versions/{version}/restore")
def restore(
    organization_id: str,
    prompt_id: str,
    version: int,
    request: Request,
    access: CanWrite,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            restored = svc.restore_version(
                db, organization_id, prompt_id, version, access.user["id"]
            )
        except svc.PromptError as exc:
            raise _invalid(exc) from exc
        if restored is None:
            raise HTTPException(status_code=404, detail="Versión no encontrada")
        _audit(db, "prompt.restore", access, request, prompt_id, organization_id, version=version)
    return restored


@router.post("/{prompt_id}/render")
def render(
    organization_id: str, prompt_id: str, body: PromptRenderRequest, access: CanRead, ctx: Ctx
) -> dict[str, Any]:
    """Devuelve el mensaje listo para enviarlo al chat (POST /api/chat). Aquí no se llama al
    modelo: el chat ya aplica límites de ritmo, guardia de temas y auditoría."""
    with ctx.database.connect() as db:
        prompt = svc.get_prompt(db, organization_id, prompt_id)
    if prompt is None:
        raise NOT_FOUND
    try:
        message = svc.chat_message(prompt, body.values)
    except svc.PromptError as exc:
        raise _invalid(exc) from exc
    if len(message) > CHAT_MAX_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"El mensaje resultante supera el máximo del chat ({CHAT_MAX_CHARS} caracteres)",
        )
    return {"message": message, "prompt_id": prompt_id, "version": prompt["version"]}
