"""Auditoría de solo anexado.

Los eventos se escriben en la misma transacción que la acción auditada. Triggers de SQLite
impiden UPDATE y DELETE; una retención futura deberá ser una migración explícita.
No se almacenan secretos: las claves sensibles de `details` se redactan.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Literal

Outcome = Literal["success", "failure", "denied"]

SENSITIVE_KEYS = frozenset({"password", "token", "secret", "authorization", "cookie", "hash"})
MAX_DETAILS_BYTES = 4096


def init_audit_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            actor_user_id TEXT,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'denied')),
            target_type TEXT,
            target_id TEXT,
            ip TEXT,
            details TEXT
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events(occurred_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action)")
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS audit_events_no_update
        BEFORE UPDATE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit_events es de solo anexado'); END
        """
    )
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
        BEFORE DELETE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit_events es de solo anexado'); END
        """
    )


def pseudonymize(value: str) -> str:
    """Identificador estable pero no reversible (p. ej. un correo en un login fallido)."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:16]


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def record_event(
    db: sqlite3.Connection,
    action: str,
    outcome: Outcome,
    *,
    actor_user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    serialized = None
    if details:
        serialized = json.dumps(_redact(details), ensure_ascii=False, default=str)
        if len(serialized.encode("utf-8")) > MAX_DETAILS_BYTES:
            serialized = json.dumps({"truncated": True})

    db.execute(
        """
        INSERT INTO audit_events
            (occurred_at, actor_user_id, action, outcome, target_type, target_id, ip, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            actor_user_id,
            action,
            outcome,
            target_type,
            target_id,
            ip,
            serialized,
        ),
    )


def list_events(
    db: sqlite3.Connection, *, limit: int = 100, action: str | None = None
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    if action:
        rows = db.execute(
            "SELECT * FROM audit_events WHERE action = ? ORDER BY id DESC LIMIT ?", (action, limit)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def count_events(
    db: sqlite3.Connection, *, action: str, outcome: Outcome, since_minutes: int
) -> int:
    """Eventos de una acción y resultado en la última ventana (usa idx_audit_action)."""
    row = db.execute(
        """
        SELECT COUNT(*) AS total FROM audit_events
        WHERE action = ? AND outcome = ?
          AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)
        """,
        (action, outcome, f"-{int(since_minutes)} minutes"),
    ).fetchone()
    return int(row["total"])
