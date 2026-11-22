"""Valida el DDL de PostgreSQL contra un servidor real (pgserver) y su paridad con SQLite.

Se omite si `pgserver`/`psycopg` no están instalados (están en requirements/dev.txt)."""

import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

if os.environ.get("NEXARO_REQUIRE_POSTGRES"):  # CI: no se admite saltarse esta validación
    import pgserver
    import psycopg
else:
    pgserver = pytest.importorskip("pgserver")
    psycopg = pytest.importorskip("psycopg")

from nexaro_api.bootstrap import migrate
from nexaro_core.database import Database

PG_DIR = Path(__file__).resolve().parents[2] / "packages/nexaro_core/database/migrations/postgresql"
IGNORED = {"schema_migrations", "sqlite_sequence"}


@pytest.fixture(scope="module")
def pg(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"))
    uri = server.get_uri()
    with psycopg.connect(uri, autocommit=True) as conn:
        conn.execute("CREATE DATABASE nexaro_test")
    with psycopg.connect(uri, dbname="nexaro_test", autocommit=True) as conn:
        for path in sorted(PG_DIR.glob("*.sql")):
            conn.execute(path.read_text())
    yield uri
    server.cleanup()


def connect(uri: str) -> Any:
    return psycopg.connect(uri, dbname="nexaro_test", autocommit=True)


def pg_columns(uri: str) -> dict[str, set[str]]:
    with connect(uri) as conn:
        rows = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        ).fetchall()
    result: dict[str, set[str]] = {}
    for table, column in rows:
        result.setdefault(table, set()).add(column)
    return result


def sqlite_columns(tmp_path: Path) -> dict[str, set[str]]:
    database = Database(tmp_path / "parity.db")
    migrate(database)
    with database.connect() as db:
        tables = [
            r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return {
            t: {c["name"] for c in db.execute(f"PRAGMA table_info({t})")}
            for t in tables
            if t not in IGNORED
        }


def test_postgres_and_sqlite_schemas_have_the_same_tables_and_columns(
    pg: str, tmp_path: Path
) -> None:
    postgres = {t: c for t, c in pg_columns(pg).items() if t not in IGNORED}
    assert postgres == sqlite_columns(tmp_path)


def test_seeded_roles_and_permissions_match_sqlite(pg: str, tmp_path: Path) -> None:
    database = Database(tmp_path / "seed.db")
    migrate(database)
    with database.connect() as db:
        expected = {
            tuple(r) for r in db.execute("SELECT role_id, permission_id FROM role_permissions")
        }
    with connect(pg) as conn:
        actual = set(conn.execute("SELECT role_id, permission_id FROM role_permissions").fetchall())
    assert actual == expected and len(actual) > 0


def seed_org(conn: Any, slug: str) -> str:
    org = uuid.uuid4()
    conn.execute(
        "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)", (org, slug, slug)
    )
    return str(org)


def test_composite_foreign_keys_reject_cross_tenant_references(pg: str) -> None:
    with connect(pg) as conn:
        a, b = seed_org(conn, "pg-a"), seed_org(conn, "pg-b")
        doc = uuid.uuid4()
        conn.execute(
            "INSERT INTO documents (id, organization_id, title) VALUES (%s, %s, 'd')", (doc, a)
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "INSERT INTO document_chunks (id, organization_id, document_id, ordinal, content) "
                "VALUES (%s, %s, %s, 0, 'x')",
                (uuid.uuid4(), b, doc),
            )
        conn.execute(
            "INSERT INTO document_chunks (id, organization_id, document_id, ordinal, content) "
            "VALUES (%s, %s, %s, 0, 'x')",
            (uuid.uuid4(), a, doc),
        )


def test_row_level_security_isolates_tenants_for_a_non_superuser(pg: str) -> None:
    with connect(pg) as conn:
        a, b = seed_org(conn, "rls-a"), seed_org(conn, "rls-b")
        for org in (a, b):
            conn.execute(
                "INSERT INTO documents (id, organization_id, title) VALUES (%s, %s, %s)",
                (uuid.uuid4(), org, f"doc-{org}"),
            )
        conn.execute("DROP ROLE IF EXISTS nexaro_app")
        conn.execute("CREATE ROLE nexaro_app NOLOGIN")
        conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexaro_app"
        )

        conn.execute("SET ROLE nexaro_app")
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0  # sin contexto

        conn.execute("SELECT set_config('nexaro.organization_id', %s, false)", (a,))
        titles = [r[0] for r in conn.execute("SELECT title FROM documents").fetchall()]
        assert titles == [f"doc-{a}"]

        with pytest.raises(psycopg.errors.InsufficientPrivilege):  # WITH CHECK: no escribe en B
            conn.execute(
                "INSERT INTO documents (id, organization_id, title) VALUES (%s, %s, 'x')",
                (uuid.uuid4(), b),
            )
        conn.execute("RESET ROLE")


def test_audit_events_are_append_only(pg: str) -> None:
    with connect(pg) as conn:
        conn.execute(
            "INSERT INTO audit_events (occurred_at, action, outcome) VALUES (now(), 't', 'success')"
        )
        with pytest.raises(psycopg.errors.RaiseException, match="solo anexado"):
            conn.execute("UPDATE audit_events SET action = 'x'")
        with pytest.raises(psycopg.errors.RaiseException, match="solo anexado"):
            conn.execute("DELETE FROM audit_events")


def test_sql_files_are_numbered_without_gaps() -> None:
    numbers = [int(re.match(r"(\d{4})_", p.name).group(1)) for p in sorted(PG_DIR.glob("*.sql"))]  # type: ignore[union-attr]
    assert numbers == list(range(1, len(numbers) + 1))
    sqlite_files = sorted((PG_DIR.parent / "sqlite").glob("*.sql"))
    assert [p.name for p in sqlite_files] == [p.name for p in sorted(PG_DIR.glob("*.sql"))][1:]
    assert sqlite3.sqlite_version  # los de SQLite empiezan en 0002: la 1 es la línea base en Python
