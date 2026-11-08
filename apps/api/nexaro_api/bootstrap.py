"""Ensamblado del esquema: orden de migraciones entre módulos."""

from nexaro_core.audit import init_audit_schema
from nexaro_core.database import Database, begin_write
from nexaro_core.identity import init_identity_schema
from products.personal_ai.schema import init_personal_ai_schema


def migrate(database: Database) -> None:
    """Migración aditiva, idempotente y atómica: ante un fallo no queda nada a medias."""
    with database.connect() as db:
        begin_write(db)
        init_personal_ai_schema(db)
        init_identity_schema(db)  # añade conversations.user_id: requiere el paso anterior
        init_audit_schema(db)
