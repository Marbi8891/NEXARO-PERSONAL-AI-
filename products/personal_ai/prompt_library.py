"""Biblioteca de prompts por organización (ADR-0023).

Integra la Prompt Library que vivía como servicio aparte (rama feature/prompt-library-mvp):
prompts con plantilla y variables, historial de versiones, restauración y un catálogo de solo
lectura que se instala en la organización. Ejecutar un prompt no pasa por aquí: el router lo
renderiza y lo envía al chat normal, que ya aplica límites, guardia y auditoría.
"""

import json
import re
import sqlite3
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOGUE_PATH = Path(__file__).parent / "data" / "prompt_catalogue.json"
VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
PLACEHOLDER = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
VARIABLE_TYPES = {"text", "textarea"}
MAX_TAGS = 12
MAX_VARIABLES = 20
MAX_VALUE_CHARS = 20_000
MAX_LIMIT = 200
EDITABLE = (
    "name",
    "description",
    "category",
    "tags",
    "system_prompt",
    "user_template",
    "variables",
)


class PromptError(Exception):
    pass


class MissingVariablesError(PromptError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__("Faltan variables: " + ", ".join(missing))
        self.missing = missing


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        value = " ".join(str(tag).split()).lower()
        if not 1 <= len(value) <= 40:
            raise PromptError("Cada etiqueta debe tener entre 1 y 40 caracteres")
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_TAGS:
        raise PromptError(f"Como máximo {MAX_TAGS} etiquetas")
    return cleaned


def _clean_variables(variables: list[dict[str, Any]], template: str) -> list[dict[str, Any]]:
    """Valida la definición de variables. Los nombres acaban en atributos HTML del frontend,
    así que se restringen a identificadores."""
    if len(variables) > MAX_VARIABLES:
        raise PromptError(f"Como máximo {MAX_VARIABLES} variables")
    cleaned: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in variables:
        name = str(raw.get("name", ""))
        if not VARIABLE_NAME.match(name):
            raise PromptError(f"Nombre de variable no válido: {name[:40]!r}")
        if name in names:
            raise PromptError(f"Variable repetida: {name}")
        names.add(name)
        kind = str(raw.get("type", "text"))
        if kind not in VARIABLE_TYPES:
            raise PromptError(f"Tipo de variable no válido: {kind[:20]!r}")
        item: dict[str, Any] = {
            "name": name,
            "label": str(raw.get("label") or name)[:80],
            "type": kind,
            "required": bool(raw.get("required", False)),
        }
        if raw.get("default") is not None:
            item["default"] = str(raw["default"])[:MAX_VALUE_CHARS]
        cleaned.append(item)
    undeclared = sorted(set(PLACEHOLDER.findall(template)) - names)
    if undeclared:
        raise PromptError("La plantilla usa variables no declaradas: " + ", ".join(undeclared))
    return cleaned


def validate(data: dict[str, Any]) -> dict[str, Any]:
    name = " ".join(str(data["name"]).split())
    category = " ".join(str(data["category"]).split())
    if not 2 <= len(name) <= 120:
        raise PromptError("El nombre debe tener entre 2 y 120 caracteres")
    if not 1 <= len(category) <= 80:
        raise PromptError("La categoría debe tener entre 1 y 80 caracteres")
    template = str(data["user_template"])
    if not template.strip():
        raise PromptError("La plantilla no puede estar vacía")
    return {
        "name": name,
        "description": str(data.get("description") or "").strip(),
        "category": category,
        "tags": _clean_tags(list(data.get("tags") or [])),
        "system_prompt": str(data.get("system_prompt") or ""),
        "user_template": template,
        "variables": _clean_variables(list(data.get("variables") or []), template),
    }


def render(prompt: dict[str, Any], values: dict[str, str]) -> str:
    """Sustituye {{variable}}. Los valores son texto literal: no se vuelven a interpretar."""
    defaults = {v["name"]: v.get("default", "") for v in prompt["variables"]}
    merged = {**defaults, **{k: str(v) for k, v in values.items()}}
    required = {v["name"] for v in prompt["variables"] if v.get("required")}
    used = set(PLACEHOLDER.findall(prompt["user_template"]))
    absent = {n for n in used if n not in merged}
    blank = {n for n in required if not merged.get(n, "").strip()}
    missing = sorted(absent | blank)
    if missing:
        raise MissingVariablesError(missing)
    if any(len(v) > MAX_VALUE_CHARS for v in merged.values()):
        raise PromptError(f"Cada valor admite como máximo {MAX_VALUE_CHARS} caracteres")
    return PLACEHOLDER.sub(lambda m: merged[m.group(1)], prompt["user_template"])


def chat_message(prompt: dict[str, Any], values: dict[str, str]) -> str:
    """Mensaje listo para el chat. El system_prompt del prompt va como instrucciones dentro del
    mensaje del usuario: nunca sustituye al prompt de sistema de la plataforma (guardia,
    identidad y reglas de seguridad siguen mandando)."""
    body = render(prompt, values)
    instructions = prompt["system_prompt"].strip()
    if not instructions:
        return body
    return f"Instrucciones del prompt «{prompt['name']}»:\n{instructions}\n\n{body}"


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "tags": json.loads(row["tags"]),
        "system_prompt": row["system_prompt"],
        "user_template": row["user_template"],
        "variables": json.loads(row["variables"]),
        "version": row["version"],
        "catalogue_id": row["catalogue_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _snapshot(data: dict[str, Any]) -> str:
    return json.dumps({k: data[k] for k in EDITABLE}, ensure_ascii=False)


def _add_version(
    db: sqlite3.Connection,
    organization_id: str,
    prompt_id: str,
    version: int,
    data: dict[str, Any],
    changelog: str,
    user_id: str,
) -> None:
    db.execute(
        """
        INSERT INTO prompt_versions (id, organization_id, prompt_id, version, snapshot,
                                     changelog, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            organization_id,
            prompt_id,
            version,
            _snapshot(data),
            changelog[:200],
            user_id,
        ),
    )


def get_prompt(
    db: sqlite3.Connection, organization_id: str, prompt_id: str
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM prompts WHERE id = ? AND organization_id = ?",
        (prompt_id, organization_id),
    ).fetchone()
    return _public(row) if row else None


def create_prompt(
    db: sqlite3.Connection,
    organization_id: str,
    user_id: str,
    data: dict[str, Any],
    *,
    changelog: str = "Versión inicial",
    catalogue_id: str | None = None,
) -> dict[str, Any]:
    """Debe llamarse dentro de una transacción de escritura."""
    clean = validate(data)
    prompt_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO prompts (id, organization_id, name, description, category, tags,
                             system_prompt, user_template, variables, catalogue_id, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            organization_id,
            clean["name"],
            clean["description"],
            clean["category"],
            json.dumps(clean["tags"], ensure_ascii=False),
            clean["system_prompt"],
            clean["user_template"],
            json.dumps(clean["variables"], ensure_ascii=False),
            catalogue_id,
            user_id,
        ),
    )
    _add_version(db, organization_id, prompt_id, 1, clean, changelog, user_id)
    created = get_prompt(db, organization_id, prompt_id)
    assert created is not None  # recién insertado en esta transacción
    return created


def update_prompt(
    db: sqlite3.Connection,
    organization_id: str,
    prompt_id: str,
    user_id: str,
    changes: dict[str, Any],
    changelog: str = "Cambios",
) -> dict[str, Any] | None:
    """Actualización parcial que crea una versión nueva. None si no existe en la organización."""
    current = get_prompt(db, organization_id, prompt_id)
    if current is None:
        return None
    clean = validate({**current, **changes})
    version = current["version"] + 1
    db.execute(
        """
        UPDATE prompts SET name = ?, description = ?, category = ?, tags = ?, system_prompt = ?,
               user_template = ?, variables = ?, version = ?,
               updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
        WHERE id = ? AND organization_id = ?
        """,
        (
            clean["name"],
            clean["description"],
            clean["category"],
            json.dumps(clean["tags"], ensure_ascii=False),
            clean["system_prompt"],
            clean["user_template"],
            json.dumps(clean["variables"], ensure_ascii=False),
            version,
            prompt_id,
            organization_id,
        ),
    )
    _add_version(db, organization_id, prompt_id, version, clean, changelog, user_id)
    return get_prompt(db, organization_id, prompt_id)


def delete_prompt(db: sqlite3.Connection, organization_id: str, prompt_id: str) -> bool:
    """Borra el prompt y su historial (ON DELETE CASCADE)."""
    cursor = db.execute(
        "DELETE FROM prompts WHERE id = ? AND organization_id = ?", (prompt_id, organization_id)
    )
    return cursor.rowcount > 0


def list_prompts(
    db: sqlite3.Connection,
    organization_id: str,
    *,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise PromptError(f"limit debe estar entre 1 y {MAX_LIMIT} y offset ser >= 0")
    clauses = ["organization_id = ?"]
    params: list[Any] = [organization_id]
    if query:
        like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append(
            "(name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
            "OR user_template LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"
        )
        params += [like] * 4
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = " AND ".join(clauses)
    rows = db.execute(
        f"SELECT * FROM prompts WHERE {where} ORDER BY COALESCE(updated_at, created_at) DESC, name",  # noqa: S608 (cláusulas fijas)
        params,
    ).fetchall()
    items = [_public(r) for r in rows]
    if tag:
        wanted = tag.strip().lower()
        items = [p for p in items if wanted in p["tags"]]
    categories = [
        r[0]
        for r in db.execute(
            "SELECT DISTINCT category FROM prompts WHERE organization_id = ? ORDER BY category",
            (organization_id,),
        )
    ]
    return {
        "total": len(items),
        "items": items[offset : offset + limit],
        "categories": categories,
    }


def list_versions(
    db: sqlite3.Connection, organization_id: str, prompt_id: str
) -> list[dict[str, Any]] | None:
    if get_prompt(db, organization_id, prompt_id) is None:
        return None
    rows = db.execute(
        """
        SELECT version, changelog, created_at, snapshot FROM prompt_versions
        WHERE prompt_id = ? AND organization_id = ? ORDER BY version DESC
        """,
        (prompt_id, organization_id),
    ).fetchall()
    return [
        {
            "version": r["version"],
            "changelog": r["changelog"],
            "created_at": r["created_at"],
            "snapshot": json.loads(r["snapshot"]),
        }
        for r in rows
    ]


def restore_version(
    db: sqlite3.Connection, organization_id: str, prompt_id: str, version: int, user_id: str
) -> dict[str, Any] | None:
    """Restaurar no reescribe el historial: crea una versión nueva con el contenido antiguo."""
    row = db.execute(
        "SELECT snapshot FROM prompt_versions WHERE prompt_id = ? AND organization_id = ? "
        "AND version = ?",
        (prompt_id, organization_id, version),
    ).fetchone()
    if row is None:
        return None
    return update_prompt(
        db,
        organization_id,
        prompt_id,
        user_id,
        json.loads(row["snapshot"]),
        changelog=f"Restaurada la versión {version}",
    )


@lru_cache(maxsize=1)
def catalogue() -> tuple[dict[str, Any], ...]:
    """Catálogo de solo lectura incluido en el código (no es dato de ninguna organización)."""
    data = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    return tuple(data["prompts"])


def catalogue_entry(catalogue_id: str) -> dict[str, Any] | None:
    return next((p for p in catalogue() if p["id"] == catalogue_id), None)


def install_from_catalogue(
    db: sqlite3.Connection, organization_id: str, user_id: str, catalogue_id: str
) -> tuple[dict[str, Any], bool] | None:
    """Copia un prompt del catálogo a la organización. Devuelve (prompt, creado) o None si el
    identificador no existe. Instalar dos veces devuelve el ya instalado."""
    entry = catalogue_entry(catalogue_id)
    if entry is None:
        return None
    existing = db.execute(
        "SELECT id FROM prompts WHERE organization_id = ? AND catalogue_id = ?",
        (organization_id, catalogue_id),
    ).fetchone()
    if existing:
        found = get_prompt(db, organization_id, existing["id"])
        assert found is not None
        return found, False
    created = create_prompt(
        db,
        organization_id,
        user_id,
        entry,
        changelog="Instalado desde el catálogo",
        catalogue_id=catalogue_id,
    )
    return created, True
