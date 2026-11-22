"""Claves de API por organización (ADR-0009).

La clave completa se devuelve una sola vez al crearla; en base de datos solo hay su hash SHA-256
(la clave tiene 256 bits de entropía aleatoria, así que no hace falta un hash lento) y un prefijo
corto para reconocerla en el listado. Una clave actúa en nombre de quien la creó y deja de valer
si se revoca, caduca, la organización se suspende, o su creador pierde la cuenta o la membresía.
"""

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

KEY_PREFIX = "nxr_"
PREFIX_LENGTH = len(KEY_PREFIX) + 6  # lo mostrado en el listado: «nxr_» + 6 caracteres
MAX_ACTIVE_KEYS = 25
SCOPES = ("chat:write", "conversations:read")
DEFAULT_SCOPES = ("chat:write",)
LAST_USED_GRANULARITY_SECONDS = 60  # evita convertir cada lectura en una escritura
_NOW = "strftime('%Y-%m-%d %H:%M:%S', 'now')"


class ApiKeyError(Exception):
    pass


class KeyLimitError(ApiKeyError):
    pass


@dataclass(frozen=True)
class ApiKeyIdentity:
    key_id: str
    organization_id: str
    user_id: str
    scopes: frozenset[str] = frozenset()

    def allows(self, scope: str) -> bool:
        return scope in self.scopes


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def create_api_key(
    db: sqlite3.Connection,
    organization_id: str,
    name: str,
    created_by: str,
    expires_in_days: int | None = None,
    scopes: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Crea una clave. Debe llamarse dentro de una transacción de escritura."""
    chosen = sorted(set(scopes or DEFAULT_SCOPES))
    unknown = [s for s in chosen if s not in SCOPES]
    if unknown:
        raise ApiKeyError(f"Permiso desconocido: {unknown[0]}")
    active = db.execute(
        f"""
        SELECT COUNT(*) AS total FROM api_keys
        WHERE organization_id = ? AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > {_NOW})
        """,  # noqa: S608  # nosec B608 - _NOW es una constante
        (organization_id,),
    ).fetchone()["total"]
    if active >= MAX_ACTIVE_KEYS:
        raise KeyLimitError(f"Se alcanzó el máximo de {MAX_ACTIVE_KEYS} claves activas")

    secret = KEY_PREFIX + secrets.token_urlsafe(32)
    key_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO api_keys
            (id, organization_id, name, prefix, key_hash, created_by, scopes, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?,
                CASE WHEN ? IS NULL THEN NULL ELSE strftime('%Y-%m-%d %H:%M:%S', 'now', ?) END)
        """,
        (
            key_id,
            organization_id,
            name,
            secret[:PREFIX_LENGTH],
            _hash(secret),
            created_by,
            ",".join(chosen),
            expires_in_days,
            f"+{expires_in_days} days",
        ),
    )
    row = db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return {**_public(row), "secret": secret}


def _public(row: sqlite3.Row) -> dict[str, Any]:
    """Nunca incluye el hash."""
    return {
        "id": row["id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "created_by": row["created_by"],
        "scopes": row["scopes"].split(","),
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "last_used_at": row["last_used_at"],
        "revoked_at": row["revoked_at"],
    }


def list_api_keys(db: sqlite3.Connection, organization_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        f"""
        SELECT k.*, u.email AS created_by_email,
               CASE WHEN k.revoked_at IS NOT NULL THEN 'revoked'
                    WHEN k.expires_at IS NOT NULL AND k.expires_at <= {_NOW} THEN 'expired'
                    ELSE 'active' END AS status
        FROM api_keys k JOIN users u ON u.id = k.created_by
        WHERE k.organization_id = ?
        ORDER BY k.created_at DESC, k.rowid DESC
        """,  # noqa: S608  # nosec B608
        (organization_id,),
    ).fetchall()
    return [
        {**_public(r), "created_by_email": r["created_by_email"], "status": r["status"]}
        for r in rows
    ]


def revoke_api_key(db: sqlite3.Connection, organization_id: str, key_id: str) -> bool:
    """Revoca una clave de la organización. Devuelve False si no existe en esa organización;
    revocar una ya revocada es idempotente y conserva la fecha original."""
    row = db.execute(
        "SELECT id FROM api_keys WHERE id = ? AND organization_id = ?", (key_id, organization_id)
    ).fetchone()
    if row is None:
        return False
    db.execute(
        f"UPDATE api_keys SET revoked_at = {_NOW} WHERE id = ? AND revoked_at IS NULL",  # noqa: S608  # nosec B608
        (key_id,),
    )
    return True


def authenticate_api_key(db: sqlite3.Connection, secret: str) -> ApiKeyIdentity | None:
    """Identidad de una clave válida, o None. No distingue el motivo del rechazo."""
    if not secret.startswith(KEY_PREFIX) or len(secret) > 200:
        return None
    row = db.execute(
        f"""
        SELECT k.id, k.organization_id, k.created_by, k.scopes
        FROM api_keys k
        JOIN organizations o ON o.id = k.organization_id AND o.status = 'active'
        JOIN users u ON u.id = k.created_by AND u.is_active = 1 AND u.approval_status = 'approved'
        JOIN memberships m ON m.organization_id = k.organization_id AND m.user_id = k.created_by
                          AND m.status = 'active'
        WHERE k.key_hash = ? AND k.revoked_at IS NULL
          AND (k.expires_at IS NULL OR k.expires_at > {_NOW})
        """,  # noqa: S608  # nosec B608
        (_hash(secret),),
    ).fetchone()
    if row is None:
        return None
    db.execute(
        f"""
        UPDATE api_keys SET last_used_at = {_NOW}
        WHERE id = ? AND (last_used_at IS NULL
              OR last_used_at <= strftime('%Y-%m-%d %H:%M:%S', 'now', ?))
        """,  # noqa: S608  # nosec B608
        (row["id"], f"-{LAST_USED_GRANULARITY_SECONDS} seconds"),
    )
    return ApiKeyIdentity(
        row["id"], row["organization_id"], row["created_by"], frozenset(row["scopes"].split(","))
    )
