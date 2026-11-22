"""Agentes de organización (ADR-0024): los mismos campos y reglas que los personales, pero
pertenecen a una organización. Los crean y cambian quienes tienen `agents:manage` (propietario y
administrador); los usan en el chat quienes tienen `agents:run` (también los miembros). Los
permisos los comprueba la API; este módulo solo filtra por organización.

Se guardan en la tabla `agents` (0002 + 0011); `system_prompt` son las instrucciones.
"""

import json
import sqlite3
import uuid
from typing import Any

from products.personal_ai import custom_agents
from products.personal_ai.agents import AGENTS
from products.personal_ai.custom_agents import (
    MAX_NAME,
    AgentNotFoundError,
    AgentProfile,
    AgentValidationError,
    validate_agent_data,
)

MAX_AGENTS_PER_ORGANIZATION = 100
FIELDS = ("name", "description", "category", "base_agent", "instructions", "tools", "model")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["instructions"] = item.pop("system_prompt")
    item["description"] = item["description"] or ""
    item["tools"] = json.loads(item["tools"])
    item["custom"] = True
    item["scope"] = "organization"
    return item


def list_agents(db: sqlite3.Connection, organization_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT id, organization_id, name, description, category, base_agent, system_prompt,"
        " tools, model, status, created_by, created_at, updated_at FROM agents"
        " WHERE organization_id = ? ORDER BY name",
        (organization_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def get_agent(db: sqlite3.Connection, organization_id: str, agent_id: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT id, organization_id, name, description, category, base_agent, system_prompt,"
        " tools, model, status, created_by, created_at, updated_at FROM agents"
        " WHERE id = ? AND organization_id = ?",
        (agent_id, organization_id),
    ).fetchone()
    if row is None:
        raise AgentNotFoundError
    return _row(row)


def _name_taken(
    db: sqlite3.Connection, organization_id: str, name: str, exclude: str | None
) -> bool:
    row = db.execute(
        "SELECT id FROM agents WHERE organization_id = ? AND lower(name) = lower(?)"
        " AND id IS NOT ?",
        (organization_id, name, exclude),
    ).fetchone()
    return row is not None


def create_agent(
    db: sqlite3.Connection, organization_id: str, user_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    clean = validate_agent_data(data)
    count = db.execute(
        "SELECT COUNT(*) FROM agents WHERE organization_id = ?", (organization_id,)
    ).fetchone()[0]
    if count >= MAX_AGENTS_PER_ORGANIZATION:
        raise AgentValidationError(
            f"La organización alcanzó el máximo de {MAX_AGENTS_PER_ORGANIZATION} agentes"
        )
    if _name_taken(db, organization_id, clean["name"], None):
        raise AgentValidationError("La organización ya tiene un agente con ese nombre")
    agent_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO agents (id, organization_id, name, description, category, base_agent,"
        " system_prompt, tools, model, status, created_by, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (
            agent_id,
            organization_id,
            clean["name"],
            clean["description"],
            clean["category"],
            clean["base_agent"],
            clean["instructions"],
            json.dumps(clean["tools"]),
            clean["model"],
            clean["status"],
            user_id,
        ),
    )
    return get_agent(db, organization_id, agent_id)


def update_agent(
    db: sqlite3.Connection, organization_id: str, agent_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    current = get_agent(db, organization_id, agent_id)
    merged = {k: current[k] for k in (*FIELDS, "status")}
    if "base_agent" in changes and "tools" not in changes:
        merged.pop("tools")  # al cambiar de base, por defecto todas las herramientas de la nueva
    merged.update(changes)
    clean = validate_agent_data(merged)
    if _name_taken(db, organization_id, clean["name"], agent_id):
        raise AgentValidationError("La organización ya tiene un agente con ese nombre")
    db.execute(
        "UPDATE agents SET name = ?, description = ?, category = ?, base_agent = ?,"
        " system_prompt = ?, tools = ?, model = ?, status = ?, updated_at = CURRENT_TIMESTAMP"
        " WHERE id = ? AND organization_id = ?",
        (
            clean["name"],
            clean["description"],
            clean["category"],
            clean["base_agent"],
            clean["instructions"],
            json.dumps(clean["tools"]),
            clean["model"],
            clean["status"],
            agent_id,
            organization_id,
        ),
    )
    return get_agent(db, organization_id, agent_id)


def duplicate_agent(
    db: sqlite3.Connection, organization_id: str, user_id: str, agent_id: str
) -> dict[str, Any]:
    """La copia nace desactivada, como la de un agente personal."""
    source = get_agent(db, organization_id, agent_id)
    name, n = f"{source['name']} (copia)"[:MAX_NAME], 2
    while _name_taken(db, organization_id, name, None):
        name = f"{source['name']} (copia {n})"[:MAX_NAME]
        n += 1
    data = {k: source[k] for k in FIELDS if k != "name"}
    return create_agent(db, organization_id, user_id, {**data, "name": name, "status": "disabled"})


def delete_agent(db: sqlite3.Connection, organization_id: str, agent_id: str) -> None:
    deleted = db.execute(
        "DELETE FROM agents WHERE id = ? AND organization_id = ?", (agent_id, organization_id)
    )
    if deleted.rowcount == 0:
        raise AgentNotFoundError


def usable_agents(db: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    """Agentes activos de las organizaciones activas en las que el usuario es miembro activo con
    permiso `agents:run`. Es la misma condición que comprueba `usable_profile`."""
    rows = db.execute(
        "SELECT a.id, a.organization_id, o.name AS organization_name, a.name, a.description,"
        " a.base_agent, a.tools, a.model FROM agents a"
        " JOIN organizations o ON o.id = a.organization_id"
        " JOIN memberships m ON m.organization_id = a.organization_id"
        " JOIN role_permissions rp ON rp.role_id = m.role_id AND rp.permission_id = 'agents:run'"
        " WHERE m.user_id = ? AND m.status = 'active' AND o.status = 'active'"
        " AND a.status = 'active' ORDER BY o.name, a.name",
        (user_id,),
    ).fetchall()
    return [
        {**dict(r), "description": r["description"] or "", "tools": json.loads(r["tools"])}
        for r in rows
    ]


def usable_profile(db: sqlite3.Connection, user_id: str, agent_id: str) -> AgentProfile:
    """Perfil de un agente de organización que el usuario puede usar ahora. Si deja de ser
    miembro, pierde `agents:run` o el agente se desactiva, AgentNotFoundError."""
    row = db.execute(
        "SELECT a.id, a.base_agent, a.system_prompt, a.tools, a.model FROM agents a"
        " JOIN organizations o ON o.id = a.organization_id"
        " JOIN memberships m ON m.organization_id = a.organization_id"
        " JOIN role_permissions rp ON rp.role_id = m.role_id AND rp.permission_id = 'agents:run'"
        " WHERE a.id = ? AND m.user_id = ? AND m.status = 'active' AND o.status = 'active'"
        " AND a.status = 'active'",
        (agent_id, user_id),
    ).fetchone()
    if row is None or row["base_agent"] not in AGENTS:
        raise AgentNotFoundError
    tools = frozenset(json.loads(row["tools"])) & AGENTS[row["base_agent"]].tools
    return AgentProfile(row["id"], row["base_agent"], row["system_prompt"], tools, row["model"])


def resolve_profile(db: sqlite3.Connection, user_id: str, agent_id: str) -> AgentProfile:
    """Perfil para el chat: un agente predefinido, uno personal activo del usuario o uno de
    organización que pueda usar. Cualquier otro caso da AgentNotFoundError."""
    try:
        return custom_agents.resolve_profile(db, user_id, agent_id)
    except AgentNotFoundError:
        if agent_id in AGENTS:
            raise
    return usable_profile(db, user_id, agent_id)
