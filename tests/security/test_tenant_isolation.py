"""Aislamiento entre organizaciones a nivel de esquema (SQLite). En PostgreSQL se añade RLS
(tests/integration/test_postgres_schema.py)."""

import sqlite3
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_core.database import Database
from nexaro_core.organizations import create_organization

# Tablas con organization_id opcional a propósito: contenido personal sin organización.
PERSONAL_OPTIONAL = {"conversations", "model_usage"}


def new_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def two_orgs(
    client: TestClient, database: Database, add_user: Callable[..., str]
) -> dict[str, str]:
    owner = add_user("owner@example.com")
    with database.connect() as db:
        a = create_organization(db, "Acme", "acme", owner)["id"]
        b = create_organization(db, "Beta", "beta", owner)["id"]
    return {"a": a, "b": b, "owner": owner}


def insert(db: sqlite3.Connection, table: str, **values: Any) -> None:
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))  # noqa: S608


def seed_chain(db: sqlite3.Connection, org: str) -> dict[str, str]:
    ids = {k: new_id() for k in ("doc", "chunk", "agent", "run", "provider")}
    insert(db, "documents", id=ids["doc"], organization_id=org, title="d")
    insert(
        db,
        "document_chunks",
        id=ids["chunk"],
        organization_id=org,
        document_id=ids["doc"],
        ordinal=0,
        content="c",
    )
    insert(
        db, "model_providers", id=ids["provider"], organization_id=org, provider="ollama", model="m"
    )
    insert(
        db,
        "agents",
        id=ids["agent"],
        organization_id=org,
        name="a",
        model_provider_id=ids["provider"],
    )
    insert(db, "agent_runs", id=ids["run"], organization_id=org, agent_id=ids["agent"])
    return ids


def test_children_must_belong_to_the_same_organization(
    database: Database, two_orgs: dict[str, str]
) -> None:
    with database.connect() as db:
        ids = seed_chain(db, two_orgs["a"])

    attempts: list[tuple[str, dict[str, Any]]] = [
        (
            "document_chunks",
            {"id": new_id(), "document_id": ids["doc"], "ordinal": 1, "content": "x"},
        ),
        (
            "embeddings",
            {
                "id": new_id(),
                "chunk_id": ids["chunk"],
                "model": "e",
                "dimensions": 3,
                "vector": b"abc",
            },
        ),
        ("agent_runs", {"id": new_id(), "agent_id": ids["agent"]}),
        ("agents", {"id": new_id(), "name": "otro", "model_provider_id": ids["provider"]}),
        ("tasks", {"id": new_id(), "title": "t", "agent_run_id": ids["run"]}),
    ]
    for table, values in attempts:
        with database.connect() as db, pytest.raises(sqlite3.IntegrityError):
            insert(db, table, organization_id=two_orgs["b"], **values)  # padre de A, hijo de B

    # Control: con la organización correcta, las mismas filas sí se aceptan.
    with database.connect() as db:
        insert(db, "agent_runs", id=new_id(), organization_id=two_orgs["a"], agent_id=ids["agent"])
        insert(
            db,
            "tasks",
            id=new_id(),
            organization_id=two_orgs["a"],
            title="t",
            agent_run_id=ids["run"],
        )


def test_deleting_an_organization_removes_all_its_data_and_only_its_data(
    database: Database, two_orgs: dict[str, str]
) -> None:
    with database.connect() as db:
        seed_chain(db, two_orgs["a"])
        seed_chain(db, two_orgs["b"])
        insert(db, "tasks", id=new_id(), organization_id=two_orgs["a"], title="t")
        db.execute("DELETE FROM organizations WHERE id = ?", (two_orgs["a"],))

    with database.connect() as db:
        for table in (
            "documents",
            "document_chunks",
            "agents",
            "agent_runs",
            "tasks",
            "model_providers",
            "memberships",
            "subscriptions",
        ):
            left = {r[0] for r in db.execute(f"SELECT DISTINCT organization_id FROM {table}")}  # noqa: S608
            assert two_orgs["a"] not in left, table
        assert (
            db.execute(
                "SELECT COUNT(*) FROM documents WHERE organization_id = ?", (two_orgs["b"],)
            ).fetchone()[0]
            == 1
        )


def test_schema_guard_every_tenant_table_is_scoped(database: Database, client: TestClient) -> None:
    """Falla si una tabla futura con organization_id omite el aislamiento en la base de datos."""
    with database.connect() as db:
        names = [
            r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        ]
        with_org = {
            n
            for n in names
            if "organization_id" in {c["name"] for c in db.execute(f"PRAGMA table_info({n})")}
        }
        assert {
            "documents",
            "document_chunks",
            "embeddings",
            "agents",
            "agent_runs",
            "tasks",
        } <= with_org

        for table in with_org - PERSONAL_OPTIONAL:
            columns = {c["name"]: c for c in db.execute(f"PRAGMA table_info({table})")}
            assert columns["organization_id"]["notnull"] == 1, (
                f"{table}.organization_id debe ser NOT NULL"
            )

        for table in with_org:
            groups: dict[int, list[sqlite3.Row]] = {}
            for fk in db.execute(f"PRAGMA foreign_key_list({table})"):
                groups.setdefault(fk["id"], []).append(fk)
            for fk_rows in groups.values():
                parent = fk_rows[0]["table"]
                if parent in with_org:
                    assert "organization_id" in {r["from"] for r in fk_rows}, (
                        f"{table} -> {parent}: la clave foránea debe incluir organization_id"
                    )


def test_personal_conversations_are_unaffected(client: TestClient, database: Database) -> None:
    with database.connect() as db:
        cols = {c["name"] for c in db.execute("PRAGMA table_info(conversations)")}
    assert {"user_id", "organization_id"} <= cols
