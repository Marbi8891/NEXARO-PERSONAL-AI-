"""Arranque de la aplicación y migración del esquema sobre bases legadas."""

import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_api import bootstrap
from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.database import Database
from tests.conftest import FakeProvider, login
from tests.legacy_db import LEGACY_EMAIL, LEGACY_PASSWORD, create_legacy_database

REAL_BACKUP = (
    Path(__file__).resolve().parents[2] / "backups" / "nexaro-pre-auth-migration-20261108.db"
)
COUNTED = ("users", "sessions", "conversations", "messages")


def counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        return {t: connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNTED}  # noqa: S608
    finally:
        connection.close()


def snapshot(path: Path) -> list[Any]:
    connection = sqlite3.connect(path)
    try:
        return sorted(connection.execute("SELECT type, name, sql FROM sqlite_master").fetchall())
    finally:
        connection.close()


def assert_migrated(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        columns = [r["name"] for r in connection.execute("PRAGMA table_info(users)")]
        assert {"role", "is_active", "approval_status"} <= set(columns)
        user = connection.execute("SELECT role, is_active, approval_status FROM users").fetchone()
        assert tuple(user) == ("user", 1, "approved")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute(
                "SELECT value FROM app_settings WHERE key = 'public_registration_enabled'"
            ).fetchone()[0]
            == "0"
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] == 0
        )
    finally:
        connection.close()


def test_lifespan_migrates_legacy_database_and_keeps_session_valid(
    settings: Settings, provider: FakeProvider
) -> None:
    user_id, token = create_legacy_database(settings.database_path)

    with TestClient(create_app(settings, chat_provider=provider)) as client:
        client.cookies.set(settings.cookie_name, token)
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"] == {"id": user_id, "email": LEGACY_EMAIL, "role": "user"}
        assert login(client, LEGACY_EMAIL, LEGACY_PASSWORD).status_code == 200

    assert counts(settings.database_path) == {
        "users": 1,
        "sessions": 5,
        "conversations": 11,
        "messages": 52,
    }
    assert_migrated(settings.database_path)


def test_fresh_database_has_registration_closed_and_no_users(
    client: TestClient, database: Database
) -> None:
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db.execute("SELECT value FROM app_settings").fetchone()[0] == "0"


def test_restart_is_idempotent(settings: Settings, provider: FakeProvider) -> None:
    create_legacy_database(settings.database_path)
    with TestClient(create_app(settings, chat_provider=provider)):
        pass
    first = snapshot(settings.database_path)
    with TestClient(create_app(settings, chat_provider=provider)):
        pass
    assert snapshot(settings.database_path) == first


def test_message_index_is_created(client: TestClient, database: Database) -> None:
    with database.connect() as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")]
    assert "idx_messages_conversation_id" in names


def test_migration_failure_aborts_startup_and_rolls_back(
    settings: Settings,
    provider: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    create_legacy_database(settings.database_path)

    def broken(db: sqlite3.Connection) -> None:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(bootstrap, "init_identity_schema", broken)

    with (
        pytest.raises(RuntimeError, match="fallo simulado"),
        TestClient(create_app(settings, chat_provider=provider)),
    ):
        pass

    assert "se aborta el arranque" in caplog.text
    connection = sqlite3.connect(settings.database_path)
    try:
        assert "role" not in [r[1] for r in connection.execute("PRAGMA table_info(users)")]
    finally:
        connection.close()


def test_migration_recreates_missing_product_tables(settings: Settings) -> None:
    create_legacy_database(settings.database_path)
    database = Database(settings.database_path)
    with database.connect() as db:
        db.execute("DROP TABLE messages")
        db.execute("DROP TABLE conversations")

    # init_personal_ai_schema recrea las tablas, así que la migración completa funciona…
    bootstrap.migrate(database)
    # …y es idempotente.
    before = snapshot(settings.database_path)
    bootstrap.migrate(database)
    assert snapshot(settings.database_path) == before


def test_missing_revoked_at_column_is_added(settings: Settings) -> None:
    create_legacy_database(settings.database_path)
    database = Database(settings.database_path)
    with database.connect() as db:
        db.execute("ALTER TABLE sessions DROP COLUMN revoked_at")
    bootstrap.migrate(database)
    with database.connect() as db:
        assert "revoked_at" in [r["name"] for r in db.execute("PRAGMA table_info(sessions)")]


@pytest.mark.skipif(not REAL_BACKUP.is_file(), reason="no hay copia real en backups/")
def test_real_backup_copy_migrates_and_original_is_untouched(tmp_path: Path) -> None:
    before = hashlib.sha256(REAL_BACKUP.read_bytes()).hexdigest()
    copy = tmp_path / "copy.db"
    shutil.copyfile(REAL_BACKUP, copy)

    database = Database(copy)
    bootstrap.migrate(database)
    first = snapshot(copy)
    bootstrap.migrate(database)

    assert snapshot(copy) == first
    assert counts(copy) == {"users": 1, "sessions": 4, "conversations": 11, "messages": 52}
    assert_migrated(copy)
    assert hashlib.sha256(REAL_BACKUP.read_bytes()).hexdigest() == before
