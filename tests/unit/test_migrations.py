import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexaro_core.database import (
    Database,
    Migration,
    MigrationError,
    backup_before_migrations,
    pending_versions,
    run_migrations,
)
from nexaro_core.database.migrations import split_statements, sql_migration


def create_table(name: str) -> Migration:
    def apply(db: sqlite3.Connection) -> None:
        db.execute(f"CREATE TABLE {name} (id INTEGER)")

    return Migration(0, name, apply, f"sum-{name}")


def numbered(*migrations: Migration) -> list[Migration]:
    return [Migration(i, m.name, m.apply, m.checksum) for i, m in enumerate(migrations, 1)]


@pytest.fixture
def database(tmp_path: Path) -> Database:
    return Database(tmp_path / "m.db")


def tables(database: Database) -> set[str]:
    with database.connect() as db:
        rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows}


def test_applies_pending_once_and_is_idempotent(database: Database) -> None:
    migrations = numbered(create_table("a"), create_table("b"))
    assert run_migrations(database, migrations) == [1, 2]
    assert run_migrations(database, migrations) == []
    assert {"a", "b", "schema_migrations"} <= tables(database)


def test_new_migrations_are_added_on_later_runs(database: Database) -> None:
    run_migrations(database, numbered(create_table("a")))
    assert run_migrations(database, numbered(create_table("a"), create_table("b"))) == [2]


def test_failure_rolls_back_the_whole_batch(database: Database) -> None:
    def boom(db: sqlite3.Connection) -> None:
        db.execute("CREATE TABLE half (id INTEGER)")
        raise RuntimeError("fallo a mitad")

    migrations = numbered(create_table("a"), Migration(0, "boom", boom, "x"))
    with pytest.raises(RuntimeError):
        run_migrations(database, migrations)
    assert tables(database) == set()  # ni 'a', ni 'half', ni schema_migrations


def test_modified_applied_migration_is_rejected(database: Database) -> None:
    run_migrations(database, numbered(create_table("a")))
    tampered = Migration(1, "a", create_table("a").apply, "otro-checksum")
    with pytest.raises(MigrationError, match="modificada"):
        run_migrations(database, [tampered])


def test_database_newer_than_code_is_rejected(database: Database) -> None:
    run_migrations(database, numbered(create_table("a"), create_table("b")))
    with pytest.raises(MigrationError, match="más antiguo"):
        run_migrations(database, numbered(create_table("a")))


def test_versions_must_be_contiguous(database: Database) -> None:
    gap = [
        Migration(1, "a", create_table("a").apply, "1"),
        Migration(3, "c", create_table("c").apply, "3"),
    ]
    with pytest.raises(MigrationError):
        run_migrations(database, gap)


def test_split_statements_handles_comments_strings_and_triggers() -> None:
    script = """
    -- comentario con ; dentro
    CREATE TABLE t (a TEXT DEFAULT 'x;y');
    CREATE TRIGGER trg BEFORE UPDATE ON t
    BEGIN SELECT RAISE(ABORT, 'no'); END;
    INSERT INTO t VALUES ('z');
    """
    statements = split_statements(script)
    assert len(statements) == 3 and statements[1].startswith("CREATE TRIGGER")


def test_incomplete_script_is_rejected() -> None:
    with pytest.raises(MigrationError):
        split_statements("CREATE TABLE t (a")


def test_sql_migration_checksum_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / "0001.sql"
    path.write_text("CREATE TABLE t (a INTEGER);")
    first = sql_migration(1, "t", path).checksum
    path.write_text("CREATE TABLE t (a INTEGER, b INTEGER);")
    assert sql_migration(1, "t", path).checksum != first


def insert_row(database: Database, table: str) -> None:
    with database.connect() as db:
        db.execute(f"INSERT INTO {table} (id) VALUES (1)")  # noqa: S608


def test_backup_is_skipped_for_a_new_database(database: Database) -> None:
    assert backup_before_migrations(database, numbered(create_table("a"))) is None
    database.ensure_parent()
    database.path.touch()  # fichero vacío: nada que proteger
    assert backup_before_migrations(database, numbered(create_table("a"))) is None


def test_backup_is_skipped_when_nothing_is_pending(database: Database) -> None:
    migrations = numbered(create_table("a"))
    run_migrations(database, migrations)
    assert pending_versions(database, migrations) == []
    assert backup_before_migrations(database, migrations) is None


def test_backup_copies_existing_data_before_pending_migrations(database: Database) -> None:
    run_migrations(database, numbered(create_table("a")))
    insert_row(database, "a")
    migrations = numbered(create_table("a"), create_table("b"))
    when = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)

    copy = backup_before_migrations(database, migrations, now=when)

    assert copy is not None
    assert copy.name.startswith("m.pre-migration-v2-20261122T150000000000Z-")
    assert copy.name.endswith(".db")
    with closing(sqlite3.connect(copy)) as db:
        assert db.execute("SELECT COUNT(*) FROM a").fetchone()[0] == 1
        assert db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 1
    run_migrations(database, migrations)
    assert "b" in tables(database)
    with closing(sqlite3.connect(copy)) as db:  # la copia no cambia al migrar
        assert db.execute("SELECT name FROM sqlite_master WHERE name = 'b'").fetchone() is None


def test_backup_covers_unversioned_legacy_databases(database: Database) -> None:
    with database.connect() as db:
        db.execute("CREATE TABLE legacy (id INTEGER)")
    assert pending_versions(database, numbered(create_table("a"))) == [1]
    assert backup_before_migrations(database, numbered(create_table("a"))) is not None


def test_backup_never_overwrites_an_existing_copy(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_migrations(database, numbered(create_table("a")))
    migrations = numbered(create_table("a"), create_table("b"))
    when = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)
    fixed_uuid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr("nexaro_core.database.migrations.uuid.uuid4", lambda: fixed_uuid)
    first = backup_before_migrations(database, migrations, now=when)
    assert first is not None
    before = first.read_bytes()
    with pytest.raises(FileExistsError):
        backup_before_migrations(database, migrations, now=when)
    assert first.read_bytes() == before
