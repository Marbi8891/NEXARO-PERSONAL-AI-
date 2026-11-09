"""Inyección SQL: ningún parámetro del usuario llega al texto de la consulta."""

import re
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from nexaro_core.database import Database
from tests.conftest import HEADERS
from tests.integration.test_documents import upload
from tests.integration.test_expenses import add, setup_org

Factory = Callable[..., TestClient]
PAYLOADS = [
    "' OR 1=1 --",
    "x'; DROP TABLE expenses; --",
    "%' UNION SELECT id, password_hash FROM users --",
    '" OR ""="',
    "\\' OR '1'='1",
]
ROOT = Path(__file__).resolve().parents[2]


def count(database: Database, table: str) -> int:
    with database.connect() as db:
        return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608


def test_expense_filters_treat_payloads_as_data(logged_in: Factory, database: Database) -> None:
    admin, org = setup_org(logged_in)
    other = admin.post(
        "/api/organizations", json={"name": "otra", "slug": "otra"}, headers=HEADERS
    ).json()["id"]
    add(admin, org, description="Hosting propio")
    add(admin, other, description="Gasto ajeno")
    users_before = count(database, "users")

    for payload in PAYLOADS:
        for query in ({"q": payload}, {"category": payload}):
            response = admin.get(f"/api/organizations/{org}/expenses", params=query)
            assert response.status_code in (200, 422), response.text
            if response.status_code == 200:
                assert response.json()["total"] == 0, payload  # no coincide nada, tampoco «todo»
        for param in ("start", "end"):
            rejected = admin.get(f"/api/organizations/{org}/expenses", params={param: payload})
            assert rejected.status_code == 422  # fechas: tipo validado antes de tocar SQL
    assert count(database, "expenses") == 2 and count(database, "users") == users_before
    assert admin.get(f"/api/organizations/{org}/expenses").json()["total"] == 1


def test_expense_summary_and_export_reject_or_ignore_payloads(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    add(admin, org)
    for payload in PAYLOADS:
        summary = admin.get(f"/api/organizations/{org}/expenses/summary", params={"month": payload})
        assert summary.status_code in (400, 422)
        export = admin.get(
            f"/api/organizations/{org}/expenses/export.csv", params={"start": payload}
        )
        assert export.status_code == 422


def test_document_search_and_audit_filter_treat_payloads_as_data(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    upload(admin, org, "Contrato", "La fianza equivale a dos mensualidades.")
    for payload in PAYLOADS:
        found = admin.get(f"/api/organizations/{org}/documents/search", params={"q": payload})
        assert found.status_code in (200, 422)
        if found.status_code == 200:
            assert found.json()["results"] == []
        events = admin.get("/api/admin/audit", params={"action": payload})
        assert events.status_code == 200 and events.json()["events"] == []
    assert count(database, "documents") == 1


def test_conversation_ids_and_chat_inputs_are_parameters(
    logged_in: Factory, database: Database
) -> None:
    client = logged_in("a@example.com")
    for payload in PAYLOADS:
        assert client.get(f"/api/conversations/{payload}").status_code == 404
        created = client.post(
            "/api/chat", json={"message": payload, "conversation_id": payload}, headers=HEADERS
        )
        assert created.status_code == 200  # el id es un valor más, no SQL
    assert count(database, "users") == 1


def test_every_interpolated_sql_fragment_is_a_fixed_constant() -> None:
    """Las pocas consultas con f-string solo interpolan nombres internos o cláusulas armadas con
    literales del propio código; este test falla si aparece una variable nueva en esos huecos."""
    allowed = {
        "products/finance/expenses.py": {"where", "_SUMMARY_COLUMNS", "_SUMMARY_FROM"},
        "packages/ai_gateway/usage.py": {"', '.join(columns)", "marks"},
        "packages/nexaro_core/api_keys/service.py": {"_NOW"},
    }
    pattern = re.compile(r'f["\'].*?(SELECT|INSERT|UPDATE|DELETE).*?["\']')
    for relative, names in allowed.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for line in text.splitlines():
            if pattern.search(line) and "noqa: S608" in line:
                for hole in re.findall(r"\{([^}]+)\}", line):
                    assert hole in names, (relative, hole)
