"""Agentes personales: crear, ver, editar, duplicar, activar/desactivar y borrar.

Solo el propietario. Un agente de otro usuario responde 404, igual que uno inexistente.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from nexaro_api.deps import Ctx, CurrentUser, client_ip, validate_origin
from nexaro_api.schemas import UserAgentCreateRequest, UserAgentUpdateRequest
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from products.personal_ai import custom_agents as store
from products.personal_ai.custom_agents import AgentNotFoundError, AgentValidationError

router = APIRouter(prefix="/api/agents/custom", tags=["agents"])

NOT_FOUND = HTTPException(status_code=404, detail="Agente no encontrado")


def _audit(ctx: Ctx, request: Request, user: dict[str, Any], action: str, agent_id: str) -> None:
    """Sin nombre ni instrucciones: son contenido del usuario."""
    with ctx.database.connect() as db:
        record_event(
            db,
            action,
            "success",
            actor_user_id=user["id"],
            target_type="agent",
            target_id=agent_id,
            ip=client_ip(request),
        )


@router.get("")
def list_custom(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {"agents": store.list_agents(db, user["id"])}


@router.post("", status_code=201)
def create_custom(
    body: UserAgentCreateRequest, request: Request, user: CurrentUser, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)
    data = body.model_dump(exclude_none=True)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            agent = store.create_agent(db, user["id"], data)
    except AgentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _audit(ctx, request, user, "agent.create", agent["id"])
    return agent


@router.get("/{agent_id}")
def get_custom(agent_id: str, user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    try:
        with ctx.database.connect() as db:
            return store.get_agent(db, user["id"], agent_id)
    except AgentNotFoundError:
        raise NOT_FOUND from None


@router.patch("/{agent_id}")
def update_custom(
    agent_id: str, body: UserAgentUpdateRequest, request: Request, user: CurrentUser, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)
    changes = body.model_dump(exclude_unset=True)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            agent = store.update_agent(db, user["id"], agent_id, changes)
    except AgentNotFoundError:
        raise NOT_FOUND from None
    except AgentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _audit(ctx, request, user, "agent.update", agent_id)
    return agent


@router.post("/{agent_id}/duplicate", status_code=201)
def duplicate_custom(
    agent_id: str, request: Request, user: CurrentUser, ctx: Ctx
) -> dict[str, Any]:
    """La copia nace desactivada: se revisa antes de usarla."""
    validate_origin(request, ctx)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            agent = store.duplicate_agent(db, user["id"], agent_id)
    except AgentNotFoundError:
        raise NOT_FOUND from None
    except AgentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _audit(ctx, request, user, "agent.duplicate", agent["id"])
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_custom(agent_id: str, request: Request, user: CurrentUser, ctx: Ctx) -> None:
    validate_origin(request, ctx)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            store.delete_agent(db, user["id"], agent_id)
    except AgentNotFoundError:
        raise NOT_FOUND from None
    _audit(ctx, request, user, "agent.delete", agent_id)
