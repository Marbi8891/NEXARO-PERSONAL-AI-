"""Registro de uso de modelos (tabla `model_usage`). Nunca guarda el contenido de los mensajes."""

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from nexaro_core.database import Database

Status = Literal["ok", "error", "denied"]


@dataclass(frozen=True)
class ModelPrice:
    """USD por 1.000 tokens."""

    input_per_1k: float
    output_per_1k: float


def estimate_cost(
    price: ModelPrice, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """None si faltan tokens: un coste desconocido no se inventa."""
    if input_tokens is None or output_tokens is None:
        return None
    return input_tokens / 1000 * price.input_per_1k + output_tokens / 1000 * price.output_per_1k


def init_usage_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS model_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            user_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ok', 'error', 'denied')),
            input_tokens INTEGER,
            output_tokens INTEGER,
            latency_ms REAL,
            cost_usd REAL,
            error_kind TEXT
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_model_usage_created ON model_usage (created_at)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_model_usage_user ON model_usage (user_id, created_at)"
    )


class UsageStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def record(
        self,
        *,
        user_id: str | None,
        provider: str,
        model: str,
        status: Status,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: float | None = None,
        cost_usd: float | None = None,
        error_kind: str | None = None,
    ) -> None:
        with self._database.connect() as db:
            db.execute(
                """
                INSERT INTO model_usage
                    (user_id, provider, model, status, input_tokens, output_tokens,
                     latency_ms, cost_usd, error_kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, provider, model, status, input_tokens, output_tokens,
                 latency_ms, cost_usd, error_kind),
            )  # fmt: skip

    def month_cost_usd(self) -> float:
        with self._database.connect() as db:
            row = db.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM model_usage
                WHERE created_at >= strftime('%Y-%m-01T00:00:00Z', 'now')
                """
            ).fetchone()
        return float(row["total"])

    def summary(self, days: int = 30) -> list[dict[str, Any]]:
        with self._database.connect() as db:
            rows = db.execute(
                """
                SELECT provider, model, status, COUNT(*) AS requests,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       SUM(cost_usd) AS cost_usd
                FROM model_usage
                WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)
                GROUP BY provider, model, status
                ORDER BY provider, model, status
                """,
                (f"-{int(days)} days",),
            ).fetchall()
        return [dict(row) for row in rows]

    def daily(self, days: int) -> list[dict[str, Any]]:
        """Peticiones y errores por día en los últimos `days` días (sin rellenar huecos)."""
        with self._database.connect() as db:
            rows = db.execute(
                """
                SELECT date(created_at) AS day, COUNT(*) AS requests,
                       COALESCE(SUM(status != 'ok'), 0) AS errors
                FROM model_usage
                WHERE created_at >= strftime('%Y-%m-%dT00:00:00Z', 'now', ?)
                GROUP BY day
                """,
                (f"-{int(days) - 1} days",),
            ).fetchall()
        return [dict(row) for row in rows]
