"""Actualización desde bases de versiones anteriores (docs/security/audits/audit-v1.md, DB-1/DB-2).

Cada versión intermedia del esquema (v1..v6) se actualiza a la actual sin perder datos, y una base
que viene de una rama con otra numeración de migraciones (p. ej. la 0008 de
`feat/renombrar-conversaciones` frente a la 0008 de `integration/security-conversation-isolation`)
se rechaza SIN tocarla.
"""

import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexaro_api.bootstrap import all_migrations, migrate
from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.database import Database, MigrationError, run_migrations
from nexaro_core.identity import create_user
from tests.conftest import ORIGIN, PASSWORD, FakeProvider, login

CURRENT = len(all_migrations())


def _database_at(path: Path, version: int) -> tuple[str, str]:
    """Base real en la versión `version` con un usuario, una conversación y dos mensajes."""
    database = Database(path)
    run_migrations(database, all_migrations()[:version])
    with database.connect() as db:
        user_id = create_user(db, "antes@example.com", PASSWORD, approved=True)
        conversation_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO conversations (id, user_id) VALUES (?, ?)", (conversation_id, user_id)
        )
        for role, content in (("user", "hola de antes"), ("assistant", "respuesta de antes")):
            db.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, role, content),
            )
    return user_id, conversation_id


def _schema(path: Path) -> list[tuple[str, str, str]]:
    connection = sqlite3.connect(path)
    try:
        return sorted(connection.execute("SELECT type, name, sql FROM sqlite_master").fetchall())
    finally:
        connection.close()


@pytest.mark.parametrize("version", range(1, CURRENT))
def test_every_previous_schema_version_upgrades_without_losing_data(
    tmp_path: Path, provider: FakeProvider, version: int
) -> None:
    path = tmp_path / "nexaro.db"
    _, conversation_id = _database_at(path, version)
    settings = Settings(
        database_path=path,
        frontend_path=tmp_path / "sin-frontend",
        allowed_origins=frozenset({ORIGIN}),
    )
    with TestClient(create_app(settings, chat_provider=provider)) as client:
        assert login(client, "antes@example.com").status_code == 200
        conversation = client.get(f"/api/conversations/{conversation_id}").json()
        assert [m["content"] for m in conversation["messages"]] == [
            "hola de antes",
            "respuesta de antes",
        ]

    connection = sqlite3.connect(path)
    try:
        versions = [r[0] for r in connection.execute("SELECT version FROM schema_migrations")]
        assert versions == list(range(1, CURRENT + 1))
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_database_from_a_branch_with_other_numbering_is_refused_untouched(tmp_path: Path) -> None:
    path = tmp_path / "nexaro.db"
    _database_at(path, CURRENT)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
            (CURRENT + 1, "conversation_title", "checksum-de-otra-rama"),
        )
    connection.close()
    before = _schema(path)

    with pytest.raises(MigrationError, match="desconocidas"):
        migrate(Database(path))
    assert _schema(path) == before


def test_same_version_with_a_different_migration_is_refused(tmp_path: Path) -> None:
    """Dos ramas que usan el mismo número para migraciones distintas: el checksum lo detecta."""
    path = tmp_path / "nexaro.db"
    _database_at(path, CURRENT)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'otra-rama' WHERE version = ?", (CURRENT,)
        )
    connection.close()
    before = _schema(path)
    with pytest.raises(MigrationError, match="modificada"):
        migrate(Database(path))
    assert _schema(path) == before


def test_migration_files_are_numbered_without_gaps_or_duplicates() -> None:
    root = Path(__file__).resolve().parents[2] / "packages/nexaro_core/database/migrations"
    for dialect in ("sqlite", "postgresql"):
        numbers = sorted(int(p.name[:4]) for p in (root / dialect).glob("*.sql"))
        assert len(numbers) == len(set(numbers)), f"números duplicados en {dialect}"
    sqlite_names = {p.name for p in (root / "sqlite").glob("*.sql")}
    postgres_names = {p.name for p in (root / "postgresql").glob("*.sql")}
    assert sqlite_names <= postgres_names  # PostgreSQL lleva además la 0001 (línea base)
