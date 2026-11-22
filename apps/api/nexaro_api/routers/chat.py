import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ai_gateway.errors import PolicyError, ProviderError
from nexaro_api.deps import (
    Ctx,
    CurrentUser,
    acquire_generation,
    check_org_permission,
    client_ip,
    validate_origin,
)
from nexaro_api.schemas import ChatRequest, ConversationRenameRequest
from nexaro_core.audit import record_event
from nexaro_core.audit.service import Outcome
from products.personal_ai import custom_agents
from products.personal_ai.agents import TOOL_PERMISSIONS, public_agents
from products.personal_ai.custom_agents import AgentNotFoundError, AgentProfile
from products.personal_ai.service import ConversationNotFoundError

router = APIRouter(prefix="/api", tags=["personal-ai"])

NOT_FOUND = HTTPException(status_code=404, detail="Conversación no encontrada")


@router.get("/agents")
def list_agents(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    """Agentes que el usuario puede usar en el chat: los predefinidos (ADR-0022) y sus agentes
    personales activos. Nunca los prompts de los predefinidos."""
    with ctx.database.connect() as db:
        own = [a for a in custom_agents.list_agents(db, user["id"]) if a["status"] == "active"]
    personal = [
        {
            "id": a["id"],
            "name": a["name"],
            "description": a["description"],
            "tools": a["tools"],
            "custom": True,
            "base_agent": a["base_agent"],
            "model": a["model"],
        }
        for a in own
    ]
    return {"agents": [*public_agents(), *personal]}


def resolve_agent(ctx: Ctx, user_id: str, agent_id: str) -> AgentProfile:
    """Perfil del agente pedido; 422 igual si no existe, es de otro usuario o está desactivado."""
    try:
        with ctx.database.connect() as db:
            return custom_agents.resolve_profile(db, user_id, agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=422, detail="Agente no disponible") from None


@router.get("/models")
async def list_models(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    """Modelos que el usuario puede elegir en el chat, descubiertos en el proveedor (no fijos
    en código). `available` false: el proveedor no responde; no se inventa la lista."""
    describe = getattr(ctx.provider, "available_models", None)
    if describe is None:
        return {
            "provider": None,
            "default_model": ctx.personal_ai.model,
            "selectable": False,
            "available": None,
            "default_installed": None,
            "fallback": [],
            "models": [],
        }
    info: dict[str, Any] = await describe()
    return info


@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    validate_origin(request, ctx)
    profile = resolve_agent(ctx, user["id"], body.agent_id)
    document_org = _document_scope(request, ctx, user, body, profile)
    lease = acquire_generation(ctx, f"user:{user['id']}")

    try:
        outcome = await ctx.personal_ai.chat(
            user["id"],
            body.message,
            body.conversation_id,
            document_organization_id=document_org,
            agent=profile.base_agent,
            model=body.model,
            profile=profile,
        )
    except ConversationNotFoundError:
        raise NOT_FOUND from None
    except PolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        # El detalle del proveedor (URLs internas, etc.) no se devuelve al cliente.
        raise HTTPException(status_code=502, detail="Error al consultar el servicio de IA") from exc
    finally:
        lease.release()

    response: dict[str, Any] = {
        "conversation_id": outcome.conversation_id,
        "answer": outcome.answer,
        "agent": body.agent_id,
    }
    if outcome.sources is not None:
        response["sources"] = outcome.sources
        _record_tool(request, ctx, user, body, "success", sources=len(outcome.sources))
    return response


def _record_tool(
    request: Request,
    ctx: Ctx,
    user: dict[str, Any],
    body: ChatRequest,
    outcome: Outcome,
    **details: Any,
) -> None:
    """Acción de un agente con una herramienta: quién, qué agente, qué herramienta y sobre qué
    organización. Nunca el contenido del mensaje ni de los documentos."""
    with ctx.database.connect() as db:
        record_event(
            db,
            "agent.tool",
            outcome,
            actor_user_id=user["id"],
            target_type="organization",
            target_id=body.document_organization_id,
            ip=client_ip(request),
            details={"agent": body.agent_id, "tool": "documents", **details},
        )


def _document_scope(
    request: Request, ctx: Ctx, user: dict[str, Any], body: ChatRequest, profile: AgentProfile
) -> str | None:
    """Documentos solo si el usuario los pide, el agente tiene la herramienta y el usuario es
    miembro con el permiso que exige."""
    if body.document_organization_id is None:
        return None
    if "documents" not in profile.tools:
        _record_tool(request, ctx, user, body, "denied", reason="agent_without_tool")
        raise HTTPException(status_code=403, detail="Este agente no puede consultar documentos")
    check_org_permission(
        ctx, request, user, body.document_organization_id, TOOL_PERMISSIONS["documents"]
    )
    return body.document_organization_id


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    request: Request, body: ChatRequest, user: CurrentUser, ctx: Ctx
) -> StreamingResponse:
    """Respuesta en streaming (SSE): start, token*, done | error."""
    validate_origin(request, ctx)
    profile = resolve_agent(ctx, user["id"], body.agent_id)
    document_org = _document_scope(request, ctx, user, body, profile)
    lease = acquire_generation(ctx, f"user:{user['id']}")
    try:
        conversation_id, events = await ctx.personal_ai.open_stream(
            user["id"],
            body.message,
            body.conversation_id,
            document_organization_id=document_org,
            agent=profile.base_agent,
            model=body.model,
            profile=profile,
        )
    except BaseException as exc:
        lease.release()
        if isinstance(exc, ConversationNotFoundError):
            raise NOT_FOUND from None
        raise

    if document_org is not None:
        _record_tool(request, ctx, user, body, "success")

    async def body_iter() -> AsyncIterator[str]:
        yield _sse({"event": "start", "conversation_id": conversation_id, "agent": body.agent_id})
        try:
            async for event in events:
                yield _sse(event)
        finally:
            # Cierra el flujo del modelo (y con él la conexión con Ollama) si el cliente se va.
            await events.aclose()  # type: ignore[attr-defined]
            lease.release()

    return StreamingResponse(
        body_iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
def list_conversations(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    return {"conversations": ctx.personal_ai.list_conversations(user["id"])}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    try:
        return ctx.personal_ai.get_conversation(user["id"], conversation_id)
    except ConversationNotFoundError:
        raise NOT_FOUND from None


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    body: ConversationRenameRequest,
    request: Request,
    user: CurrentUser,
    ctx: Ctx,
) -> dict[str, Any]:
    """Título propio para una conversación del usuario; 404 si no existe o es de otro."""
    validate_origin(request, ctx)
    try:
        title = ctx.personal_ai.rename_conversation(user["id"], conversation_id, body.title)
    except ConversationNotFoundError:
        raise NOT_FOUND from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    with ctx.database.connect() as db:
        # Sin el título en la auditoría: es contenido del usuario.
        record_event(
            db,
            "conversation.rename",
            "success",
            actor_user_id=user["id"],
            target_type="conversation",
            target_id=conversation_id,
            ip=client_ip(request),
        )
    return {"id": conversation_id, "title": title}


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, request: Request, user: CurrentUser, ctx: Ctx
) -> None:
    validate_origin(request, ctx)
    # Mismo tope de operaciones simultáneas por usuario que el chat, sin gastar su ritmo por minuto.
    lease = acquire_generation(ctx, f"user:{user['id']}", rate_limit=False)
    try:
        try:
            ctx.personal_ai.delete_conversation(user["id"], conversation_id)
        except ConversationNotFoundError:
            raise NOT_FOUND from None
        with ctx.database.connect() as db:
            record_event(
                db,
                "conversation.delete",
                "success",
                actor_user_id=user["id"],
                target_type="conversation",
                target_id=conversation_id,
                ip=client_ip(request),
            )
    finally:
        lease.release()
