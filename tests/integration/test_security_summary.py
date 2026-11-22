"""Resumen de seguridad: solo administradores, solo datos reales y sin datos personales."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from nexaro_core.audit import pseudonymize, record_event
from nexaro_core.database import Database
from tests.conftest import ORIGIN, PASSWORD

Factory = Callable[..., TestClient]
URL = "/api/admin/security"


def seed(database: Database) -> None:
    with database.connect() as db:
        for _ in range(3):
            record_event(
                db, "auth.login", "failure", ip="10.0.0.1", target_id=pseudonymize("a@x.io")
            )
        record_event(db, "auth.login", "failure", ip="10.0.0.2")
        record_event(db, "auth.login", "success", ip="10.0.0.9")
        record_event(db, "authz.admin_required", "denied", ip="10.0.0.3")
        record_event(db, "authz.permission_denied", "denied", ip="10.0.0.3")
        record_event(db, "auth.lockout", "denied", ip="10.0.0.1")


def insert_old(database: Database, days_ago: int, action: str = "auth.login") -> None:
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    with database.connect() as db:
        db.execute(
            "INSERT INTO audit_events (occurred_at, action, outcome, ip)"
            " VALUES (?, ?, 'failure', ?)",
            (when, action, "10.9.9.9"),
        )


def test_requires_an_administrator(logged_in: Factory, client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    user = logged_in("user@example.com")
    assert user.get(URL).status_code == 403


def test_empty_system_is_all_zeros_not_invented(logged_in: Factory) -> None:
    admin = logged_in("admin@example.com", role="admin")
    data = admin.get(URL).json()
    assert data["days"] == 14
    assert data["totals"] == {
        "failed_logins": 0,
        "denied": 0,
        "lockouts": 0,
        "successful_logins": 1,
    }
    assert len(data["daily"]) == 14
    assert all(d["failed_logins"] == d["denied"] == d["lockouts"] == 0 for d in data["daily"])
    assert data["top_ips"] == [] and data["by_action"] == []
    assert [e["action"] for e in data["recent"]] == []


def test_aggregates_real_events(logged_in: Factory, database: Database) -> None:
    admin = logged_in("admin@example.com", role="admin")
    seed(database)

    data = admin.get(URL).json()

    assert data["totals"] == {
        "failed_logins": 4,
        "denied": 2,
        "lockouts": 1,
        "successful_logins": 2,
    }
    today = datetime.now(timezone.utc).date().isoformat()
    assert data["daily"][-1] == {"date": today, "failed_logins": 4, "denied": 2, "lockouts": 1}
    assert data["top_ips"] == [
        {"ip": "10.0.0.1", "failed_logins": 3},
        {"ip": "10.0.0.2", "failed_logins": 1},
    ]
    counts = {(r["action"], r["outcome"]): r["count"] for r in data["by_action"]}
    assert counts[("auth.login", "failure")] == 4
    assert counts[("authz.admin_required", "denied")] == 1
    assert ("auth.login", "success") not in counts  # solo incidencias
    recent = data["recent"]
    assert [e["id"] for e in recent] == sorted((e["id"] for e in recent), reverse=True)
    assert {e["outcome"] for e in recent} <= {"failure", "denied"}


def test_window_excludes_old_events_and_days_widens_it(
    logged_in: Factory, database: Database
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    insert_old(database, days_ago=5)

    assert admin.get(f"{URL}?days=3").json()["totals"]["failed_logins"] == 0
    wide = admin.get(f"{URL}?days=7").json()
    assert wide["totals"]["failed_logins"] == 1
    assert wide["daily"][-6]["failed_logins"] == 1  # hace 5 días = 6.º desde el final
    assert admin.get(f"{URL}?days=3").json()["top_ips"] == []


def test_days_is_clamped(logged_in: Factory) -> None:
    admin = logged_in("admin@example.com", role="admin")
    assert admin.get(f"{URL}?days=0").json()["days"] == 1
    assert admin.get(f"{URL}?days=500").json()["days"] == 90


def test_response_has_no_emails_pseudonyms_or_details(
    logged_in: Factory, database: Database
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    seed(database)
    with database.connect() as db:
        record_event(db, "auth.login", "failure", ip="10.0.0.5", details={"password": "x"})

    raw = admin.get(URL).text

    assert pseudonymize("a@x.io") not in raw and "a@x.io" not in raw
    assert "details" not in raw and "target_id" not in raw


def test_a_real_failed_login_shows_up(logged_in: Factory, client: TestClient) -> None:
    admin = logged_in("admin@example.com", role="admin")
    wrong = {"email": "admin@example.com", "password": PASSWORD + "x"}
    assert client.post("/api/auth/login", json=wrong, headers={"Origin": ORIGIN}).status_code == 401

    data = admin.get(URL).json()

    assert data["totals"]["failed_logins"] == 1
    assert data["top_ips"][0]["failed_logins"] == 1
