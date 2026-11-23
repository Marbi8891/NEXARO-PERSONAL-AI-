"""Registro persistente de agentes personalizados por organización.

En esta fase los agentes son perfiles de prompt. Las herramientas ejecutables no se habilitan:
el runtime todavía no implementa un sandbox ni un dispatcher de herramientas.
"""
import json
import sqlite3
import uuid
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from nexaro_api.deps import Ctx, OrgAccess, client_ip, require_permission, validate_origin
from nexaro_api.schemas import AgentCreateRequest, AgentUpdateRequest
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write

router = APIRouter(prefix="/api/organizations/{organization_id}/agents", tags=["agents"])
CanRead = Annotated[OrgAccess, Depends(require_permission("agents:read"))]
CanManage = Annotated[OrgAccess, Depends(require_permission("agents:manage"))]

_SAFE_PERMISSIONS = {"filesystem": "none", "terminal": False, "network": False}
_MEMORY_SCOPES = {"none", "conversation", "workspace", "global"}


def _validate_config(body: AgentCreateRequest) -> None:
    # Capabilities are deliberately not user-grantable until the tool runtime and sandbox exist.
    if body.tools:
        raise HTTPException(
            status_code=422, detail="Las herramientas ejecutables aún no están disponibles"
        )
    if body.permissions != _SAFE_PERMISSIONS:
        raise HTTPException(
            status_code=422,
            detail="Este runtime solo admite agentes sin permisos de ejecución",
        )
    if set(body.memory) - {"enabled", "scope"} or not isinstance(
        body.memory.get("enabled", False), bool
    ):
        raise HTTPException(status_code=422, detail="Configuración de memoria no válida")
    if body.memory.get("scope", "none") not in _MEMORY_SCOPES:
        raise HTTPException(status_code=422, detail="Ámbito de memoria no válido")
    if body.memory.get("enabled", False) or body.memory.get("scope", "none") != "none":
        raise HTTPException(
            status_code=422, detail="La memoria operativa aún no está disponible"
        )
    if body.autonomy != "assisted":
        raise HTTPException(status_code=422, detail="La autonomía ejecutable aún no está disponible")


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for field in ("tools_json", "permissions_json", "memory_json"):
        item[field.removesuffix("_json")] = json.loads(item.pop(field) or "{}")
    return item


@router.get("")
def list_agents(organization_id: str, access: CanRead, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        rows = db.execute(
            "SELECT * FROM agents WHERE organization_id = ? ORDER BY created_at DESC, name",
            (organization_id,),
        ).fetchall()
    return {"agents": [_serialize(row) for row in rows]}


@router.post("", status_code=201)
def create_agent(
    organization_id: str,
    body: AgentCreateRequest,
    request: Request,
    access: CanManage,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    _validate_config(body)
    agent_id = str(uuid.uuid4())
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            db.execute(
                """INSERT INTO agents
                   (id, organization_id, name, description, system_prompt, status, created_by,
                    category, model, tools_json, permissions_json, memory_json, autonomy,
                    template_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (
                    agent_id,
                    organization_id,
                    body.name.strip(),
                    body.description.strip(),
                    body.system_prompt.strip(),
                    access.user["id"],
                    body.category,
                    body.model.strip() if body.model else None,
                    json.dumps(body.tools),
                    json.dumps(body.permissions),
                    json.dumps(body.memory),
                    body.autonomy,
                    body.template_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Ya existe un agente con ese nombre") from exc
        record_event(
            db,
            "agent.create",
            "success",
            actor_user_id=access.user["id"],
            target_type="agent",
            target_id=agent_id,
            ip=client_ip(request),
            details={"organization": organization_id, "category": body.category},
        )
        row = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _serialize(row)


@router.get("/{agent_id}")
def get_agent(
    organization_id: str, agent_id: str, access: CanRead, ctx: Ctx
) -> dict[str, Any]:
    with ctx.database.connect() as db:
        row = db.execute(
            "SELECT * FROM agents WHERE id = ? AND organization_id = ?",
            (agent_id, organization_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return _serialize(row)


@router.put("/{agent_id}")
def update_agent(
    organization_id: str,
    agent_id: str,
    body: AgentUpdateRequest,
    request: Request,
    access: CanManage,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    _validate_config(body)
    with ctx.database.connect() as db:
        begin_write(db)
        exists = db.execute(
            "SELECT id FROM agents WHERE id = ? AND organization_id = ?",
            (agent_id, organization_id),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        try:
            db.execute(
                """UPDATE agents SET name=?, description=?, system_prompt=?, status=?,
                   category=?, model=?, tools_json=?, permissions_json=?, memory_json=?,
                   autonomy=?, template_id=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND organization_id=?""",
                (
                    body.name.strip(),
                    body.description.strip(),
                    body.system_prompt.strip(),
                    body.status,
                    body.category,
                    body.model.strip() if body.model else None,
                    json.dumps(body.tools),
                    json.dumps(body.permissions),
                    json.dumps(body.memory),
                    body.autonomy,
                    body.template_id,
                    agent_id,
                    organization_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Ya existe un agente con ese nombre") from exc
        record_event(
            db,
            "agent.update",
            "success",
            actor_user_id=access.user["id"],
            target_type="agent",
            target_id=agent_id,
            ip=client_ip(request),
            details={"organization": organization_id, "status": body.status},
        )
        row = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _serialize(row)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(
    organization_id: str,
    agent_id: str,
    request: Request,
    access: CanManage,
    ctx: Ctx,
) -> None:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        deleted = db.execute(
            "DELETE FROM agents WHERE id = ? AND organization_id = ?",
            (agent_id, organization_id),
        ).rowcount
        if not deleted:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        record_event(
            db,
            "agent.delete",
            "success",
            actor_user_id=access.user["id"],
            target_type="agent",
            target_id=agent_id,
            ip=client_ip(request),
            details={"organization": organization_id},
        )
