"""Autorización, aislamiento entre usuarios, abuso y auditoría."""

import sqlite3
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from nexaro_core.audit import list_events, record_event
from nexaro_core.database import Database
from nexaro_core.identity import LastAdminError, ensure_not_last_admin
from tests.conftest import HEADERS, PASSWORD, audit_actions, login

pytestmark = pytest.mark.security


def test_protected_routes_require_authentication(client: TestClient) -> None:
    for method, path in (
        ("get", "/api/auth/me"),
        ("get", "/api/conversations"),
        ("get", "/api/conversations/x"),
        ("post", "/api/chat"),
        ("get", "/api/admin/users"),
        ("get", "/api/admin/audit"),
    ):
        assert getattr(client, method)(path, headers=HEADERS).status_code == 401, path


@pytest.mark.parametrize("origin", [None, "https://evil.example"])
def test_state_changing_routes_reject_missing_or_foreign_origin(
    client: TestClient, add_user: Callable[..., str], origin: str | None
) -> None:
    add_user("a@example.com")
    headers = {"Origin": origin} if origin else {}
    payload = {"email": "a@example.com", "password": PASSWORD}
    assert client.post("/api/auth/login", json=payload, headers=headers).status_code == 403
    assert client.post("/api/auth/logout", headers=headers).status_code == 403


def test_admin_routes_reject_normal_users_and_audit_the_denial(
    logged_in: Callable[..., TestClient], database: Database
) -> None:
    user = logged_in("user@example.com")
    assert user.get("/api/admin/users").status_code == 403
    assert user.get("/api/admin/audit").status_code == 403
    assert (
        user.post(
            "/api/admin/users",
            json={"email": "n@example.com", "password": PASSWORD},
            headers=HEADERS,
        ).status_code
        == 403
    )
    assert (
        user.patch(
            "/api/admin/settings/registration", json={"enabled": True}, headers=HEADERS
        ).status_code
        == 403
    )
    assert "authz.admin_required" in audit_actions(database)


def test_admin_list_never_exposes_password_hashes(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    response = admin.get("/api/admin/users")
    assert response.status_code == 200
    assert "password" not in response.text.lower()


def test_admin_actions_require_origin(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    assert (
        admin.patch("/api/admin/settings/registration", json={"enabled": True}).status_code == 403
    )


def test_admin_created_user_is_never_admin_and_short_password_is_rejected(
    logged_in: Callable[..., TestClient],
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    created = admin.post(
        "/api/admin/users", json={"email": "new@example.com", "password": PASSWORD}, headers=HEADERS
    )
    assert created.status_code == 201 and created.json()["role"] == "user"
    short = admin.post(
        "/api/admin/users", json={"email": "s@example.com", "password": "corta"}, headers=HEADERS
    )
    assert short.status_code == 422


@pytest.mark.parametrize("action", ["reject", "deactivate"])
def test_reject_and_deactivate_revoke_live_sessions(
    logged_in: Callable[..., TestClient], add_user: Callable[..., str], action: str
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    user = logged_in("target@example.com")
    user_id = user.get("/api/auth/me").json()["user"]["id"]

    if action == "reject":
        response = admin.post(f"/api/admin/users/{user_id}/reject", headers=HEADERS)
    else:
        response = admin.patch(
            f"/api/admin/users/{user_id}/active", json={"active": False}, headers=HEADERS
        )

    assert response.status_code == 200
    assert user.get("/api/auth/me").status_code == 401


def test_admin_cannot_reject_or_deactivate_self(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    me = admin.get("/api/auth/me").json()["user"]["id"]
    assert admin.post(f"/api/admin/users/{me}/reject", headers=HEADERS).status_code == 400
    assert (
        admin.patch(
            f"/api/admin/users/{me}/active", json={"active": False}, headers=HEADERS
        ).status_code
        == 400
    )
    assert admin.get("/api/auth/me").status_code == 200


def test_last_active_admin_is_protected(
    client: TestClient, add_user: Callable[..., str], database: Database
) -> None:
    only = add_user("admin@example.com", role="admin")
    with database.connect() as db, pytest.raises(LastAdminError):
        ensure_not_last_admin(db, only)

    other = add_user("admin2@example.com", role="admin")
    with database.connect() as db:
        ensure_not_last_admin(db, only)
        ensure_not_last_admin(db, other)


def test_unknown_user_returns_404(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    assert admin.post("/api/admin/users/nope/approve", headers=HEADERS).status_code == 404


def test_users_cannot_read_or_write_each_others_conversations(
    logged_in: Callable[..., TestClient],
) -> None:
    alice, bob = logged_in("alice@example.com"), logged_in("bob@example.com")
    conversation_id = alice.post(
        "/api/chat", json={"message": "secreto de alice"}, headers=HEADERS
    ).json()["conversation_id"]

    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 200
    assert bob.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert (
        bob.post(
            "/api/chat",
            json={"message": "intruso", "conversation_id": conversation_id},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert bob.get("/api/conversations").json()["conversations"] == []


def test_account_is_locked_after_repeated_failures(
    client: TestClient, add_user: Callable[..., str], settings
) -> None:
    add_user("a@example.com")
    for _ in range(settings.login_max_attempts):
        assert login(client, "a@example.com", "mala-clave-1234").status_code == 401
    assert login(client, "a@example.com").status_code == 429


def test_successful_login_does_not_reset_the_ip_counter(
    client: TestClient, add_user: Callable[..., str], settings
) -> None:
    add_user("valid@example.com")
    for index in range(settings.login_max_attempts - 1):
        login(client, f"x{index}@example.com", "mala-clave-1234")

    assert login(client, "valid@example.com").status_code == 200
    login(client, "y@example.com", "mala-clave-1234")
    assert login(client, "valid@example.com").status_code == 429


def test_lockout_is_audited_once_not_per_request(
    client: TestClient, add_user: Callable[..., str], database: Database, settings
) -> None:
    add_user("a@example.com")
    for _ in range(settings.login_max_attempts + 5):
        login(client, "a@example.com", "mala-clave-1234")
    assert audit_actions(database).count("auth.lockout") == 1


def test_audit_trail_records_logins_and_admin_actions_without_secrets(
    logged_in: Callable[..., TestClient], client: TestClient, database: Database
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    login(client, "ghost@example.com", "mala-clave-1234")
    admin.patch("/api/admin/settings/registration", json={"enabled": True}, headers=HEADERS)

    actions = audit_actions(database)
    assert {"auth.login", "admin.registration_toggle"} <= set(actions)

    events = admin.get("/api/admin/audit").json()["events"]
    dump = str(events).lower()
    assert "ghost@example.com" not in dump  # el correo se registra seudonimizado
    assert "mala-clave" not in dump and PASSWORD not in dump


def test_audit_log_is_append_only(client: TestClient, database: Database) -> None:
    with database.connect() as db:
        record_event(db, "test.event", "success")
    with database.connect() as db, pytest.raises(sqlite3.DatabaseError, match="solo anexado"):
        db.execute("UPDATE audit_events SET action = 'x'")
    with database.connect() as db, pytest.raises(sqlite3.DatabaseError, match="solo anexado"):
        db.execute("DELETE FROM audit_events")
    with database.connect() as db:
        assert list_events(db, action="test.event")


def test_audit_redacts_sensitive_detail_keys(client: TestClient, database: Database) -> None:
    with database.connect() as db:
        record_event(
            db,
            "test.redact",
            "success",
            details={"password": "p", "nested": {"token": "t", "ok": 1}},
        )
        event = list_events(db, action="test.redact")[0]
    assert (
        "REDACTED" in event["details"]
        and '"p"' not in event["details"]
        and '"t"' not in event["details"]
    )
