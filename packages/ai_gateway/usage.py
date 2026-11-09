"""Registro de uso de modelos (tabla `model_usage`). Nunca guarda el contenido de los mensajes."""

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from ai_gateway.schemas import InferenceMetrics
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
        organization_id: str | None = None,
        api_key_id: str | None = None,
        metrics: InferenceMetrics | None = None,
    ) -> None:
        columns = {
            "user_id": user_id, "provider": provider, "model": model, "status": status,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "latency_ms": latency_ms, "cost_usd": cost_usd, "error_kind": error_kind,
        }  # fmt: skip
        # Las columnas de organización y clave las añade la migración 3: solo con valor.
        if organization_id is not None:
            columns["organization_id"] = organization_id
        if api_key_id is not None:
            columns["api_key_id"] = api_key_id
        if metrics is not None:  # columnas de la migración 6
            columns.update(
                ttft_ms=metrics.ttft_ms,
                load_ms=metrics.load_ms,
                prompt_eval_ms=metrics.prompt_eval_ms,
                generation_ms=metrics.generation_ms,
            )
        marks = ", ".join("?" for _ in columns)
        with self._database.connect() as db:
            db.execute(
                f"INSERT INTO model_usage ({', '.join(columns)}) VALUES ({marks})",  # noqa: S608
                tuple(columns.values()),
            )

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

    def inference(self, days: int) -> list[dict[str, Any]]:
        """Rendimiento medio por modelo (solo peticiones correctas con métricas): TTFT, carga y
        tokens/s. Medias, no medianas: SQLite no tiene mediana; sirven para ver tendencias."""
        with self._database.connect() as db:
            rows = db.execute(
                """
                SELECT provider, model, COUNT(*) AS requests,
                       AVG(ttft_ms) AS avg_ttft_ms, AVG(load_ms) AS avg_load_ms,
                       AVG(prompt_eval_ms) AS avg_prompt_eval_ms,
                       AVG(latency_ms) AS avg_total_ms,
                       AVG(CASE WHEN generation_ms > 0 THEN output_tokens * 1000.0 / generation_ms
                           END) AS avg_tokens_per_second,
                       SUM(load_ms > 1000) AS cold_loads
                FROM model_usage
                WHERE status = 'ok' AND ttft_ms IS NOT NULL
                  AND created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)
                GROUP BY provider, model
                ORDER BY provider, model
                """,
                (f"-{int(days)} days",),
            ).fetchall()
        return [
            {k: (round(v, 1) if isinstance(v, float) else v) for k, v in dict(row).items()}
            for row in rows
        ]

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

    def by_api_key(self, organization_id: str, days: int) -> list[dict[str, Any]]:
        """Uso de la organización por clave de API en los últimos `days` días (una consulta)."""
        with self._database.connect() as db:
            rows = db.execute(
                """
                SELECT u.api_key_id AS key_id, k.name, k.prefix, COUNT(*) AS requests,
                       COALESCE(SUM(u.status != 'ok'), 0) AS errors,
                       COALESCE(SUM(u.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(u.output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(u.cost_usd), 0.0) AS cost_usd
                FROM model_usage u LEFT JOIN api_keys k ON k.id = u.api_key_id
                WHERE u.organization_id = ?
                  AND u.created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)
                GROUP BY u.api_key_id
                ORDER BY requests DESC
                """,
                (organization_id, f"-{int(days)} days"),
            ).fetchall()
        return [dict(row) for row in rows]
