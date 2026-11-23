"""Agentes de organización (ADR-0024): verlos con `agents:read`, crearlos, editarlos,
duplicarlos y borrarlos con `agents:manage` (propietario y administrador). Usarlos en el chat
pide `agents:run`, que se comprueba al resolver el agente.

No ser miembro es un 404 de la organización; un agente de otra organización, 404 del agente.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from nexaro_api.deps import Ctx, OrgAccess, client_ip, require_permission, validate_origin
from nexaro_api.schemas import UserAgentCreateRequest, UserAgentUpdateRequest
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from products.personal_ai import org_agents as store
from products.personal_ai.custom_agents import AgentNotFoundError, AgentValidationError

router = APIRouter(prefix="/api/organizations/{organization_id}/agents", tags=["agents"])

CanRead = Annotated[OrgAccess, Depends(require_permission("agents:read"))]
CanManage = Annotated[OrgAccess, Depends(require_permission("agents:manage"))]

NOT_FOUND = HTTPException(status_code=404, detail="Agente no encontrado")


def _audit(
    ctx: Ctx, request: Request, access: OrgAccess, action: str, organization_id: str, agent_id: str
) -> None:
    """Sin nombre ni instrucciones: son contenido de la organización."""
    with ctx.database.connect() as db:
        record_event(
            db,
            action,
            "success",
            actor_user_id=access.user["id"],
            target_type="agent",
            target_id=agent_id,
            ip=client_ip(request),
            details={"organization": organization_id},
        )


@router.get("")
def list_org_agents(organization_id: str, access: CanRead, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {"agents": store.list_agents(db, organization_id)}


@router.post("", status_code=201)
def create_org_agent(
    organization_id: str,
    body: UserAgentCreateRequest,
    request: Request,
    access: CanManage,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            agent = store.create_agent(
                db, organization_id, access.user["id"], body.model_dump(exclude_none=True)
            )
    except AgentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _audit(ctx, request, access, "org_agent.create", organization_id, agent["id"])
    return agent


@router.get("/{agent_id}")
def get_org_agent(organization_id: str, agent_id: str, access: CanRead, ctx: Ctx) -> dict[str, Any]:
    try:
        with ctx.database.connect() as db:
            return store.get_agent(db, organization_id, agent_id)
    except AgentNotFoundError:
        raise NOT_FOUND from None


@router.patch("/{agent_id}")
def update_org_agent(
    organization_id: str,
    agent_id: str,
    body: UserAgentUpdateRequest,
    request: Request,
    access: CanManage,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            agent = store.update_agent(
                db, organization_id, agent_id, body.model_dump(exclude_unset=True)
            )
    except AgentNotFoundError:
        raise NOT_FOUND from None
    except AgentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _audit(ctx, request, access, "org_agent.update", organization_id, agent_id)
    return agent


@router.post("/{agent_id}/duplicate", status_code=201)
def duplicate_org_agent(
    organization_id: str, agent_id: str, request: Request, access: CanManage, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            agent = store.duplicate_agent(db, organization_id, access.user["id"], agent_id)
    except AgentNotFoundError:
        raise NOT_FOUND from None
    except AgentValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _audit(ctx, request, access, "org_agent.duplicate", organization_id, agent["id"])
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_org_agent(
    organization_id: str, agent_id: str, request: Request, access: CanManage, ctx: Ctx
) -> None:
    validate_origin(request, ctx)
    try:
        with ctx.database.connect() as db:
            begin_write(db)
            store.delete_agent(db, organization_id, agent_id)
    except AgentNotFoundError:
        raise NOT_FOUND from None
    _audit(ctx, request, access, "org_agent.delete", organization_id, agent_id)
