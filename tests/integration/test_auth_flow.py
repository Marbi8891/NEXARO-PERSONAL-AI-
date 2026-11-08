from collections.abc import Callable
from unittest.mock import patch

from fastapi.testclient import TestClient

from nexaro_core.config import Settings
from tests.conftest import HEADERS, PASSWORD, login


def test_login_sets_secure_session_cookie(client: TestClient, add_user: Callable[..., str]) -> None:
    add_user("a@example.com")
    response = login(client, "a@example.com")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    for flag in ("httponly", "samesite=strict", "path=/", "max-age="):
        assert flag in cookie
    assert "password" not in response.text.lower()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "a@example.com"


def test_session_cookie_max_age_follows_settings(
    client: TestClient, add_user: Callable[..., str], settings: Settings
) -> None:
    add_user("a@example.com")
    cookie = login(client, "a@example.com").headers["set-cookie"].lower()
    assert f"max-age={settings.session_max_age_seconds}" in cookie


def test_login_is_case_insensitive(client: TestClient, add_user: Callable[..., str]) -> None:
    add_user("a@example.com")
    assert login(client, "A@Example.COM").status_code == 200


def test_wrong_password_and_unknown_user_are_indistinguishable(
    client: TestClient, add_user: Callable[..., str]
) -> None:
    add_user("a@example.com")
    wrong = login(client, "a@example.com", "otra-clave-distinta")
    unknown = login(client, "nadie@example.com")

    assert (wrong.status_code, unknown.status_code) == (401, 401)
    assert wrong.json() == unknown.json()


def test_pending_and_inactive_accounts_cannot_login(
    client: TestClient, add_user: Callable[..., str]
) -> None:
    add_user("pending@example.com", approved=False)
    add_user("inactive@example.com", active=False)
    for email in ("pending@example.com", "inactive@example.com"):
        assert login(client, email).status_code == 401


def test_unknown_user_still_runs_password_verification(client: TestClient) -> None:
    with patch("nexaro_core.identity.service.verify_password", return_value=False) as verify:
        login(client, "nadie@example.com")
    verify.assert_called_once()


def test_logout_revokes_the_session_server_side(
    client: TestClient, app, add_user: Callable[..., str], settings: Settings
) -> None:
    add_user("a@example.com")
    login(client, "a@example.com")
    token = client.cookies.get(settings.cookie_name)

    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 200

    replay = TestClient(app)
    replay.cookies.set(settings.cookie_name, token)
    assert replay.get("/api/auth/me").status_code == 401


def test_public_registration_flow(
    client: TestClient, app, logged_in: Callable[..., TestClient]
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    public = TestClient(app)
    body = {"email": "new@example.com", "password": PASSWORD}

    assert public.post("/api/auth/register", json=body, headers=HEADERS).status_code == 403
    assert (
        admin.patch(
            "/api/admin/settings/registration", json={"enabled": True}, headers=HEADERS
        ).status_code
        == 200
    )

    created = public.post("/api/auth/register", json=body, headers=HEADERS)
    assert created.status_code == 201
    assert created.json()["approval_status"] == "pending"
    assert login(public, "new@example.com").status_code == 401

    user_id = created.json()["user_id"]
    assert admin.post(f"/api/admin/users/{user_id}/approve", headers=HEADERS).status_code == 200
    assert login(public, "new@example.com").status_code == 200
    assert public.get("/api/auth/me").json()["user"]["role"] == "user"


def test_duplicate_registration_returns_409(
    client: TestClient, app, logged_in: Callable[..., TestClient]
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    admin.patch("/api/admin/settings/registration", json={"enabled": True}, headers=HEADERS)
    body = {"email": "dup@example.com", "password": PASSWORD}
    public = TestClient(app)
    assert public.post("/api/auth/register", json=body, headers=HEADERS).status_code == 201
    assert public.post("/api/auth/register", json=body, headers=HEADERS).status_code == 409
