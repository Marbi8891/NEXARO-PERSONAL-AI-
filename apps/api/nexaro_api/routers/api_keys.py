"""Módulo Developer: claves de API de una organización, su uso y el endpoint público /api/v1."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_gateway.errors import PolicyError, ProviderError
from ai_gateway.usage import UsageStore
from nexaro_api.deps import (
    ChatKey,
    Ctx,
    OrgAccess,
    ReadKey,
    acquire_generation,
    client_ip,
    require_permission,
    validate_origin,
)
from nexaro_api.schemas import ApiKeyCreateRequest, ChatRequest
from nexaro_core.api_keys import ApiKeyError, KeyLimitError, create_api_key, list_api_keys
from nexaro_core.api_keys import revoke_api_key as revoke
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from products.personal_ai.service import ConversationNotFoundError

router = APIRouter(tags=["developer"])

CanManageKeys = Annotated[OrgAccess, Depends(require_permission("api_keys:manage"))]
CanReadUsage = Annotated[OrgAccess, Depends(require_permission("usage:read"))]
MAX_DAYS = 90


@router.get("/api/organizations/{organization_id}/api-keys")
def keys(organization_id: str, access: CanManageKeys, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {"api_keys": list_api_keys(db, organization_id)}


@router.post("/api/organizations/{organization_id}/api-keys", status_code=201)
def create(
    organization_id: str,
    body: ApiKeyCreateRequest,
    request: Request,
    access: CanManageKeys,
    ctx: Ctx,
) -> dict[str, Any]:
    """La respuesta incluye `secret`, la única vez que se muestra la clave completa."""
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            created = create_api_key(
                db,
                organization_id,
                body.name.strip(),
                access.user["id"],
                body.expires_in_days,
                body.scopes,
            )
        except KeyLimitError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ApiKeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_event(
            db,
            "apikey.create",
            "success",
            actor_user_id=access.user["id"],
            target_type="api_key",
            target_id=created["id"],
            ip=client_ip(request),
            details={
                "organization": organization_id,
                "name": created["name"],
                "scopes": created["scopes"],
            },
        )
    return created


@router.delete("/api/organizations/{organization_id}/api-keys/{key_id}", status_code=204)
def revoke_api_key(
    organization_id: str, key_id: str, request: Request, access: CanManageKeys, ctx: Ctx
) -> None:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        if not revoke(db, organization_id, key_id):
            raise HTTPException(status_code=404, detail="Clave no encontrada")
        record_event(
            db,
            "apikey.revoke",
            "success",
            actor_user_id=access.user["id"],
            target_type="api_key",
            target_id=key_id,
            ip=client_ip(request),
            details={"organization": organization_id},
        )


@router.get("/api/organizations/{organization_id}/usage")
def usage(organization_id: str, access: CanReadUsage, ctx: Ctx, days: int = 30) -> dict[str, Any]:
    """Uso de la organización por clave de API (solo lo que pasó por una clave)."""
    days = min(max(days, 1), MAX_DAYS)
    rows = UsageStore(ctx.database).by_api_key(organization_id, days)
    return {"days": days, "keys": rows}


@router.post("/api/v1/chat")
async def public_chat(body: ChatRequest, key: ChatKey, ctx: Ctx) -> dict[str, Any]:
    # Ya hay límite por minuto y clave (key_limiter); aquí solo el tope de generaciones.
    lease = acquire_generation(ctx, f"key:{key.key_id}", rate_limit=False)
    try:
        outcome = await ctx.personal_ai.chat(
            key.user_id,
            body.message,
            body.conversation_id,
            organization_id=key.organization_id,
            api_key_id=key.key_id,
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversación no encontrada") from None
    except PolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail="Error al consultar el servicio de IA") from exc
    finally:
        lease.release()
    return {"conversation_id": outcome.conversation_id, "answer": outcome.answer}


@router.get("/api/v1/conversations")
def public_conversations(key: ReadKey, ctx: Ctx, limit: int = 50) -> dict[str, Any]:
    """Conversaciones creadas con claves de la organización de esta clave (no el chat web)."""
    limit = min(max(limit, 1), 100)
    rows = ctx.personal_ai.list_conversations(
        key.user_id, limit=limit, organization_id=key.organization_id
    )
    return {"conversations": rows}


@router.get("/api/v1/conversations/{conversation_id}")
def public_conversation(conversation_id: str, key: ReadKey, ctx: Ctx) -> dict[str, Any]:
    try:
        return ctx.personal_ai.get_conversation(
            key.user_id, conversation_id, organization_id=key.organization_id
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversación no encontrada") from None
