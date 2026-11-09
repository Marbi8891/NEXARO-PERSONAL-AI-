"""Servicios de identidad: usuarios, sesiones y registro. Operan sobre una conexión abierta;
quien llama decide la transacción. No dependen de FastAPI."""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from nexaro_core.identity.errors import LastAdminError
from nexaro_core.security import (
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


def _utc_timestamp(value: datetime | None = None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria")

    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def create_session(
    db: sqlite3.Connection,
    user_id: str,
    lifetime: timedelta = timedelta(days=7),
    now: datetime | None = None,
) -> str:
    """Crea una sesión sin confirmar la transacción de SQLite.

    El llamador es responsable de hacer commit o rollback.
    """
    if not isinstance(lifetime, timedelta) or lifetime.total_seconds() <= 0:
        raise ValueError("La duración de la sesión debe ser positiva")

    base_time = now or datetime.now(timezone.utc)
    _utc_timestamp(base_time)
    expires_at = _utc_timestamp(base_time + lifetime)

    token = create_session_token()
    session_id = str(uuid.uuid4())

    db.execute(
        """
        INSERT INTO sessions (id, user_id, token_hash, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, user_id, hash_session_token(token), expires_at),
    )

    return token


def get_session_user(
    db: sqlite3.Connection,
    token: str,
    now: datetime | None = None,
) -> sqlite3.Row | None:
    if not isinstance(token, str) or not token:
        return None

    current_time = _utc_timestamp(now)

    row: sqlite3.Row | None = db.execute(
        """
        SELECT users.id, users.email, users.role
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ?
          AND sessions.revoked_at IS NULL
          AND sessions.expires_at > ?
          AND users.is_active = 1
          AND users.approval_status = 'approved'
        LIMIT 1
        """,
        (hash_session_token(token), current_time),
    ).fetchone()
    return row


def revoke_session(
    db: sqlite3.Connection,
    token: str,
    now: datetime | None = None,
) -> bool:
    if not isinstance(token, str) or not token:
        return False

    revoked_at = _utc_timestamp(now)

    cursor = db.execute(
        """
        UPDATE sessions
        SET revoked_at = ?
        WHERE token_hash = ?
          AND revoked_at IS NULL
        """,
        (revoked_at, hash_session_token(token)),
    )

    return cursor.rowcount == 1


def create_user(
    db: sqlite3.Connection,
    email: str,
    password: str,
    approved: bool = False,
) -> str:
    """Crea una cuenta normal. Nunca asigna el rol admin."""
    if not isinstance(email, str):
        raise ValueError("Correo electrónico no válido")

    normalized_email = email.strip().lower()

    if (
        len(normalized_email) > 254
        or normalized_email.count("@") != 1
        or "." not in normalized_email.rsplit("@", 1)[-1]
    ):
        raise ValueError("Correo electrónico no válido")

    password_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    status = "approved" if approved else "pending"
    active = 1 if approved else 0

    db.execute(
        """
        INSERT INTO users (
            id, email, password_hash, role, is_active, approval_status
        )
        VALUES (?, ?, ?, 'user', ?, ?)
        """,
        (user_id, normalized_email, password_hash, active, status),
    )

    return user_id


def approve_user(db: sqlite3.Connection, user_id: str) -> bool:
    cursor = db.execute(
        """
        UPDATE users
        SET approval_status = 'approved', is_active = 1
        WHERE id = ?
        """,
        (user_id,),
    )
    return cursor.rowcount == 1


def reject_user(db: sqlite3.Connection, user_id: str) -> bool:
    cursor = db.execute(
        """
        UPDATE users
        SET approval_status = 'rejected', is_active = 0
        WHERE id = ?
        """,
        (user_id,),
    )
    return cursor.rowcount == 1


def set_user_active(
    db: sqlite3.Connection,
    user_id: str,
    active: bool,
) -> bool:
    if not isinstance(active, bool):
        raise ValueError("El estado activo debe ser booleano")

    cursor = db.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if active else 0, user_id),
    )
    return cursor.rowcount == 1


def set_user_role(
    db: sqlite3.Connection,
    user_id: str,
    role: str,
) -> bool:
    if role not in ("admin", "user"):
        raise ValueError("Rol no válido")

    cursor = db.execute(
        "UPDATE users SET role = ? WHERE id = ?",
        (role, user_id),
    )
    return cursor.rowcount == 1


def count_active_admins(
    db: sqlite3.Connection,
    excluding_user_id: str | None = None,
) -> int:
    """Cuenta administradores activos y aprobados, opcionalmente sin uno."""
    row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE role = 'admin'
          AND is_active = 1
          AND approval_status = 'approved'
          AND id IS NOT ?
        """,
        (excluding_user_id,),
    ).fetchone()
    return int(row["total"])


def list_users(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        """
        SELECT id, email, role, is_active, approval_status, created_at
        FROM users
        ORDER BY created_at DESC, email COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def user_counts(db: sqlite3.Connection) -> dict[str, int]:
    """Totales de cuentas en una consulta: total, pendientes e inactivas aprobadas."""
    row = db.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(approval_status = 'pending'), 0) AS pending,
               COALESCE(SUM(approval_status = 'approved' AND is_active = 0), 0) AS inactive
        FROM users
        """
    ).fetchone()
    return {
        "total": int(row["total"]),
        "pending": int(row["pending"]),
        "inactive": int(row["inactive"]),
    }


def get_registration_enabled(db: sqlite3.Connection) -> bool:
    row = db.execute(
        """
        SELECT value FROM app_settings
        WHERE key = 'public_registration_enabled'
        """
    ).fetchone()
    return row is not None and row["value"] == "1"


def set_registration_enabled(
    db: sqlite3.Connection,
    enabled: bool,
) -> None:
    if not isinstance(enabled, bool):
        raise ValueError("El estado del registro debe ser booleano")

    db.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('public_registration_enabled', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        ("1" if enabled else "0",),
    )


@lru_cache
def _dummy_hash() -> str:
    # Hash de relleno: un login con cuenta inexistente/pendiente/inactiva cuesta lo mismo que uno
    # válido (evita enumeración de cuentas por tiempo de respuesta).
    return hash_password("nexaro-dummy-password")


def authenticate(db: sqlite3.Connection, email: str, password: str) -> sqlite3.Row | None:
    user = db.execute(
        """
        SELECT id, email, password_hash, role
        FROM users
        WHERE email = ? COLLATE NOCASE
          AND is_active = 1
          AND approval_status = 'approved'
        LIMIT 1
        """,
        (email.strip(),),
    ).fetchone()

    password_ok = verify_password(password, user["password_hash"] if user else _dummy_hash())
    return user if (user is not None and password_ok) else None


def revoke_user_sessions(db: sqlite3.Connection, user_id: str) -> int:
    cursor = db.execute(
        "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (_utc_timestamp(), user_id),
    )
    return cursor.rowcount


def ensure_not_last_admin(db: sqlite3.Connection, user_id: str) -> None:
    """Impide dejar el sistema sin administradores activos."""
    target = db.execute(
        "SELECT role, is_active, approval_status FROM users WHERE id = ?", (user_id,)
    ).fetchone()

    if (
        target is not None
        and target["role"] == "admin"
        and target["is_active"] == 1
        and target["approval_status"] == "approved"
        and count_active_admins(db, excluding_user_id=user_id) == 0
    ):
        raise LastAdminError("No se puede desactivar al último administrador activo")
