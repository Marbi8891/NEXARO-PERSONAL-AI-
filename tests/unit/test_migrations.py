import sqlite3
from pathlib import Path

import pytest

from nexaro_core.database import Database, Migration, MigrationError, run_migrations
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
