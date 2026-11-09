"""Gastos por organización: validación, resumen, exportación CSV, aislamiento y permisos."""

from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient

from nexaro_core.database import Database
from products.finance import expenses as svc
from tests.conftest import ORIGIN, audit_actions

HEADERS = {"Origin": ORIGIN}
Factory = Callable[..., TestClient]


def setup_org(logged_in: Factory, slug: str = "acme") -> tuple[TestClient, str]:
    admin = logged_in("owner@example.com", role="admin")
    org = admin.post("/api/organizations", json={"name": slug, "slug": slug}, headers=HEADERS)
    return admin, str(org.json()["id"])


def add(admin: TestClient, org: str, **overrides: object) -> dict:
    body = {
        "spent_on": "2026-10-15",
        "description": "Hosting",
        "amount_cents": 1210,
        "vat_cents": 210,
        "category": "Software",
        **overrides,
    }
    response = admin.post(f"/api/organizations/{org}/expenses", json=body, headers=HEADERS)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_create_normalizes_and_lists_with_totals(logged_in: Factory, database: Database) -> None:
    admin, org = setup_org(logged_in)
    created = add(admin, org, category="  Software  Cloud ", vendor="  OVH ")
    assert created["category"] == "software cloud" and created["vendor"] == "OVH"
    assert created["amount_cents"] == 1210 and created["currency"] == "EUR"
    add(admin, org, description="Dominio", amount_cents=1000, vat_cents=0, category="software")

    listed = admin.get(f"/api/organizations/{org}/expenses").json()
    assert (
        listed["total"] == 2 and listed["total_cents"] == 2210 and listed["total_vat_cents"] == 210
    )
    assert listed["categories"] == ["software", "software cloud"]
    assert {"expense.create"} <= set(audit_actions(database))


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount_cents": 0},
        {"amount_cents": -5},
        {"amount_cents": 100_000_001},
        {"amount_cents": 1000, "vat_cents": 1001},
        {"vat_cents": -1},
        {"description": ""},
        {"category": ""},
        {"category": "x" * 41},
        {"spent_on": "1999-12-31"},
        {"spent_on": "2999-01-01"},
        {"spent_on": "no-es-fecha"},
    ],
)
def test_invalid_expenses_are_rejected(logged_in: Factory, overrides: dict) -> None:
    admin, org = setup_org(logged_in)
    body = {
        "spent_on": "2026-10-15",
        "description": "x",
        "amount_cents": 1000,
        "category": "otros",
        **overrides,
    }
    response = admin.post(f"/api/organizations/{org}/expenses", json=body, headers=HEADERS)
    assert response.status_code == 422, overrides
    assert admin.get(f"/api/organizations/{org}/expenses").json()["total"] == 0


def test_writes_require_origin(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    body = {"spent_on": "2026-10-15", "description": "x", "amount_cents": 100, "category": "a"}
    assert admin.post(f"/api/organizations/{org}/expenses", json=body).status_code == 403


def test_filters_by_date_category_and_text(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    add(admin, org, spent_on="2026-09-01", description="Licencia IDE", category="software")
    add(admin, org, spent_on="2026-10-10", description="Tren a Valencia", category="viajes")
    add(
        admin,
        org,
        spent_on="2026-10-20",
        description="Anuncio",
        vendor="Meta",
        category="marketing",
    )
    path = f"/api/organizations/{org}/expenses"

    def titles(**params: str) -> list[str]:
        rows = admin.get(path, params=params).json()["expenses"]
        return [r["description"] for r in rows]

    assert titles() == ["Anuncio", "Tren a Valencia", "Licencia IDE"]  # más reciente primero
    assert titles(start="2026-10-01", end="2026-10-15") == ["Tren a Valencia"]
    assert titles(category="VIAJES") == ["Tren a Valencia"]
    assert titles(q="meta") == ["Anuncio"] and titles(q="licencia") == ["Licencia IDE"]
    assert admin.get(path, params={"limit": 1, "offset": 1}).json()["expenses"][0][
        "description"
    ] == ("Tren a Valencia")
    assert admin.get(path, params={"start": "no"}).status_code == 422


def test_update_and_delete(logged_in: Factory, database: Database) -> None:
    admin, org = setup_org(logged_in)
    expense = add(admin, org)
    path = f"/api/organizations/{org}/expenses/{expense['id']}"

    changed = admin.patch(path, json={"amount_cents": 2000, "vat_cents": 347}, headers=HEADERS)
    assert changed.status_code == 200 and changed.json()["amount_cents"] == 2000
    assert changed.json()["updated_at"] is not None
    assert admin.patch(path, json={"vat_cents": 5000}, headers=HEADERS).status_code == 422
    assert admin.patch(path, json={}, headers=HEADERS).status_code == 422
    assert admin.patch(path, json={"description": None}, headers=HEADERS).status_code == 422
    cleared = admin.patch(path, json={"vendor": None}, headers=HEADERS)
    assert cleared.status_code == 200 and cleared.json()["vendor"] is None

    assert admin.delete(path, headers=HEADERS).status_code == 204
    assert admin.delete(path, headers=HEADERS).status_code == 404
    assert admin.patch(path, json={"description": "x"}, headers=HEADERS).status_code == 404
    assert admin.get(f"/api/organizations/{org}/expenses").json()["total"] == 0
    assert {"expense.update", "expense.delete"} <= set(audit_actions(database))


def test_monthly_summary_by_category_and_six_month_history(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    add(admin, org, spent_on="2026-10-01", amount_cents=1000, vat_cents=100, category="software")
    add(admin, org, spent_on="2026-10-31", amount_cents=3000, vat_cents=0, category="viajes")
    add(admin, org, spent_on="2026-10-15", amount_cents=500, vat_cents=0, category="software")
    add(admin, org, spent_on="2026-08-10", amount_cents=700, vat_cents=0, category="software")
    add(admin, org, spent_on="2026-11-02", amount_cents=999, vat_cents=0, category="software")
    path = f"/api/organizations/{org}/expenses/summary"

    body = admin.get(path, params={"month": "2026-10"}).json()
    assert body["month"] == "2026-10" and body["count"] == 3 and body["total_cents"] == 4500
    assert body["vat_cents"] == 100
    assert body["by_category"] == [
        {"category": "viajes", "total_cents": 3000, "count": 1},
        {"category": "software", "total_cents": 1500, "count": 2},
    ]
    assert [h["month"] for h in body["history"]] == [
        "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
    ]  # fmt: skip
    assert [h["total_cents"] for h in body["history"]] == [0, 0, 0, 700, 0, 4500]
    # el límite entre meses no se mezcla (31 de octubre / 1-2 de noviembre)
    assert admin.get(path, params={"month": "2026-11"}).json()["total_cents"] == 999
    assert admin.get(path, params={"month": "2026-13"}).status_code == 422
    assert admin.get(path).json()["month"] == date.today().strftime("%Y-%m")
    year_end = admin.get(path, params={"month": "2026-12"}).json()
    assert year_end["history"][-1]["month"] == "2026-12" and year_end["total_cents"] == 0


def test_csv_export_is_spreadsheet_ready_and_neutralizes_formulas(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    add(admin, org, description='=HYPERLINK("http://x")', vendor="+cmd", amount_cents=123456)
    add(
        admin,
        org,
        description='Café; con "comillas"',
        spent_on="2026-10-01",
        amount_cents=5,
        vat_cents=0,
    )

    response = admin.get(f"/api/organizations/{org}/expenses/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    assert text.startswith("﻿fecha;descripcion;proveedor;categoria;importe_eur;iva_eur\r\n")
    lines = text.split("\r\n")
    assert lines[1].startswith('2026-10-01;"Café; con ""comillas""";;software;0,05;')
    assert "'=HYPERLINK" in lines[2] and ";'+cmd;" in lines[2]
    assert "1234,56" in lines[2]
    assert "expense.export" in audit_actions(database)
    assert (
        admin.get(f"/api/organizations/{org}/expenses/export.csv?start=2026-10-10").text.count(
            "\r\n"
        )
        == 2
    )


def test_euro_format_has_no_float_errors() -> None:
    assert (
        svc._euros(5) == "0,05"
        and svc._euros(100) == "1,00"
        and svc._euros(99999999) == "999999,99"
    )


def test_expenses_are_isolated_between_organizations(logged_in: Factory) -> None:
    admin, acme = setup_org(logged_in)
    beta = admin.post(
        "/api/organizations", json={"name": "Beta", "slug": "beta"}, headers=HEADERS
    ).json()["id"]
    expense = add(admin, acme)

    assert admin.get(f"/api/organizations/{beta}/expenses").json()["total"] == 0
    assert admin.get(f"/api/organizations/{beta}/expenses/summary").json()["total_cents"] == 0
    other = f"/api/organizations/{beta}/expenses/{expense['id']}"
    assert admin.patch(other, json={"description": "x"}, headers=HEADERS).status_code == 404
    assert admin.delete(other, headers=HEADERS).status_code == 404
    assert admin.get(f"/api/organizations/{acme}/expenses").json()["total"] == 1
    assert admin.get(f"/api/organizations/{beta}/expenses/export.csv").text.count("\r\n") == 1


def test_only_owner_and_admin_roles_see_finances(logged_in: Factory, add_user: Callable) -> None:
    admin, org = setup_org(logged_in)
    for email, role in (("m@example.com", "member"), ("v@example.com", "viewer")):
        add_user(email)
        admin.post(
            f"/api/organizations/{org}/members",
            json={"email": email, "role": role},
            headers=HEADERS,
        )
    outsider = logged_in("out@example.com")
    path = f"/api/organizations/{org}/expenses"
    body = {"spent_on": "2026-10-15", "description": "x", "amount_cents": 100, "category": "a"}

    for email in ("m@example.com", "v@example.com"):
        client = TestClient(admin.app)
        client.post(
            "/api/auth/login",
            json={"email": email, "password": "correct-horse-battery"},
            headers=HEADERS,
        )
        assert client.get(path).status_code == 403
        assert client.get(f"{path}/summary").status_code == 403
        assert client.get(f"{path}/export.csv").status_code == 403
        assert client.post(path, json=body, headers=HEADERS).status_code == 403
    assert outsider.get(path).status_code == 404
