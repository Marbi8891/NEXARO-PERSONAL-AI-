"""Ensamblado del esquema: orden de migraciones entre módulos (ADR-0005)."""

import sqlite3

from ai_gateway.usage import init_usage_schema
from nexaro_core.audit import init_audit_schema
from nexaro_core.database import Database, Migration, platform_migrations, run_migrations
from nexaro_core.identity import init_identity_schema
from products.personal_ai.schema import init_personal_ai_schema


def _baseline(db: sqlite3.Connection) -> None:
    """Esquema anterior al versionado. Idempotente: en una base viva no cambia nada."""
    init_personal_ai_schema(db)
    init_identity_schema(db)  # añade conversations.user_id: requiere el paso anterior
    init_audit_schema(db)
    init_usage_schema(db)


def all_migrations() -> list[Migration]:
    return [Migration(1, "baseline", _baseline, "baseline-v1"), *platform_migrations()]


def migrate(database: Database) -> None:
    """Aplica las pendientes en una sola transacción: si falla, no queda nada a medias."""
    run_migrations(database, all_migrations())
