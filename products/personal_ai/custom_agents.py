"""Agentes personales: cada usuario crea los suyos a partir de un agente predefinido.

Un agente personal hereda las reglas de su agente base (identidad, seguridad y
confidencialidad no se pueden quitar) y añade instrucciones propias. Sus herramientas son, como
máximo, las del agente base: el usuario solo puede quitar, nunca añadir. Solo su propietario lo
ve, lo usa o lo cambia; para cualquier otro usuario no existe.
"""

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from products.personal_ai.agents import AGENTS

MAX_NAME = 80
MAX_DESCRIPTION = 300
MAX_CATEGORY = 40
MAX_INSTRUCTIONS = 4000
MAX_AGENTS_PER_USER = 50
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
STATUSES = ("active", "disabled")


class AgentNotFoundError(Exception):
    pass


class AgentValidationError(ValueError):
    """Mensaje apto para el usuario."""


@dataclass(frozen=True)
class AgentProfile:
    """Lo que el chat necesita para usar un agente: reglas base, instrucciones, herramientas y
    modelo por defecto. `record_id` es lo que se guarda en `messages.agent`."""

    record_id: str
    base_agent: str
    instructions: str
    tools: frozenset[str]
    model: str | None


def _clean(value: str, limit: int, field: str, *, required: bool = False) -> str:
    text = value.strip()
    if required and not text:
        raise AgentValidationError(f"El campo «{field}» es obligatorio")
    if len(text) > limit:
        raise AgentValidationError(f"El campo «{field}» no puede superar {limit} caracteres")
    return text


def validate_agent_data(data: dict[str, Any]) -> dict[str, Any]:
    base = data.get("base_agent", "general")
    if base not in AGENTS:
        raise AgentValidationError("Agente base desconocido")
    allowed = AGENTS[base].tools
    tools = sorted(set(data.get("tools", sorted(allowed))))
    extra = set(tools) - allowed
    if extra:
        raise AgentValidationError(
            f"El agente base «{base}» no tiene estas herramientas: {', '.join(sorted(extra))}"
        )
    model = data.get("model")
    if model == "auto":
        model = None
    if model is not None and not MODEL_PATTERN.match(model):
        raise AgentValidationError("Nombre de modelo no válido")
    status = data.get("status", "active")
    if status not in STATUSES:
        raise AgentValidationError("Estado no válido")
    return {
        "name": _clean(data.get("name", ""), MAX_NAME, "nombre", required=True),
        "description": _clean(data.get("description", ""), MAX_DESCRIPTION, "descripción"),
        "category": _clean(data.get("category", "general"), MAX_CATEGORY, "categoría") or "general",
        "base_agent": base,
        "instructions": _clean(data.get("instructions", ""), MAX_INSTRUCTIONS, "instrucciones"),
        "tools": tools,
        "model": model,
        "status": status,
    }


def _row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tools"] = json.loads(item["tools"])
    item.pop("owner_user_id", None)
    item["custom"] = True
    return item


def list_agents(db: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT id, owner_user_id, name, description, category, base_agent, instructions, tools,"
        " model, status, created_at, updated_at FROM user_agents"
        " WHERE owner_user_id = ? ORDER BY name",
        (user_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def get_agent(db: sqlite3.Connection, user_id: str, agent_id: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT id, owner_user_id, name, description, category, base_agent, instructions, tools,"
        " model, status, created_at, updated_at FROM user_agents"
        " WHERE id = ? AND owner_user_id = ?",
        (agent_id, user_id),
    ).fetchone()
    if row is None:
        raise AgentNotFoundError
    return _row(row)


def _name_taken(db: sqlite3.Connection, user_id: str, name: str, exclude: str | None) -> bool:
    row = db.execute(
        "SELECT id FROM user_agents WHERE owner_user_id = ? AND lower(name) = lower(?)"
        " AND id IS NOT ?",
        (user_id, name, exclude),
    ).fetchone()
    return row is not None


def create_agent(db: sqlite3.Connection, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    clean = validate_agent_data(data)
    count = db.execute(
        "SELECT COUNT(*) FROM user_agents WHERE owner_user_id = ?", (user_id,)
    ).fetchone()[0]
    if count >= MAX_AGENTS_PER_USER:
        raise AgentValidationError(f"Se alcanzó el máximo de {MAX_AGENTS_PER_USER} agentes")
    if _name_taken(db, user_id, clean["name"], None):
        raise AgentValidationError("Ya tienes un agente con ese nombre")
    agent_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO user_agents (id, owner_user_id, name, description, category, base_agent,"
        " instructions, tools, model, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            agent_id,
            user_id,
            clean["name"],
            clean["description"],
            clean["category"],
            clean["base_agent"],
            clean["instructions"],
            json.dumps(clean["tools"]),
            clean["model"],
            clean["status"],
        ),
    )
    return get_agent(db, user_id, agent_id)


def update_agent(
    db: sqlite3.Connection, user_id: str, agent_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    current = get_agent(db, user_id, agent_id)
    merged = {
        k: current[k]
        for k in (
            "name",
            "description",
            "category",
            "base_agent",
            "instructions",
            "tools",
            "model",
            "status",
        )
    }
    if "base_agent" in changes and "tools" not in changes:
        merged.pop("tools")  # al cambiar de base, por defecto todas las herramientas de la nueva
    merged.update(changes)
    clean = validate_agent_data(merged)
    if _name_taken(db, user_id, clean["name"], agent_id):
        raise AgentValidationError("Ya tienes un agente con ese nombre")
    db.execute(
        "UPDATE user_agents SET name = ?, description = ?, category = ?, base_agent = ?,"
        " instructions = ?, tools = ?, model = ?, status = ?, updated_at = CURRENT_TIMESTAMP"
        " WHERE id = ? AND owner_user_id = ?",
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
            user_id,
        ),
    )
    return get_agent(db, user_id, agent_id)


def duplicate_agent(db: sqlite3.Connection, user_id: str, agent_id: str) -> dict[str, Any]:
    source = get_agent(db, user_id, agent_id)
    base_name = f"{source['name']} (copia)"[:MAX_NAME]
    name, n = base_name, 2
    while _name_taken(db, user_id, name, None):
        name = f"{source['name']} (copia {n})"[:MAX_NAME]
        n += 1
    data = {
        k: source[k]
        for k in ("description", "category", "base_agent", "instructions", "tools", "model")
    }
    return create_agent(db, user_id, {**data, "name": name, "status": "disabled"})


def delete_agent(db: sqlite3.Connection, user_id: str, agent_id: str) -> None:
    deleted = db.execute(
        "DELETE FROM user_agents WHERE id = ? AND owner_user_id = ?", (agent_id, user_id)
    )
    if deleted.rowcount == 0:
        raise AgentNotFoundError


def resolve_profile(db: sqlite3.Connection, user_id: str, agent_id: str) -> AgentProfile:
    """Perfil para el chat. Un agente predefinido, o uno personal activo del usuario; cualquier
    otro id (de otro usuario, desactivado o inexistente) da AgentNotFoundError."""
    if agent_id in AGENTS:
        builtin = AGENTS[agent_id]
        return AgentProfile(agent_id, agent_id, "", builtin.tools, None)
    try:
        uuid.UUID(agent_id)
    except ValueError:
        raise AgentNotFoundError from None
    agent = get_agent(db, user_id, agent_id)
    if agent["status"] != "active":
        raise AgentNotFoundError
    tools = frozenset(agent["tools"]) & AGENTS[agent["base_agent"]].tools
    return AgentProfile(
        agent["id"], agent["base_agent"], agent["instructions"], tools, agent["model"]
    )
