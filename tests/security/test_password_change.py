"""Cambio de contraseña del propio usuario (SECURITY_REVIEW_V1.md, AUTH-1)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import HEADERS, PASSWORD, audit_actions, login

pytestmark = pytest.mark.security
NEW = "otra-clave-muy-larga-2026"


def change(client: TestClient, current: str, new: str, headers: Any = HEADERS) -> Any:
    return client.post(
        "/api/auth/password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


def test_requires_session_and_origin(
    client: TestClient, logged_in: Callable[..., TestClient]
) -> None:
    assert change(client, PASSWORD, NEW).status_code == 401
    user = logged_in("a@example.com")
    assert change(user, PASSWORD, NEW, headers={"Origin": "https://evil.test"}).status_code == 403
    assert change(user, PASSWORD, NEW, headers={}).status_code == 403


def test_change_keeps_this_session_revokes_others_and_audits(
    app: Any, logged_in: Callable[..., TestClient], database: Any
) -> None:
    first = logged_in("a@example.com")
    second = TestClient(app)
    assert login(second, "a@example.com").status_code == 200

    response = change(first, PASSWORD, NEW)
    assert response.status_code == 200
    assert response.json() == {"changed": True, "other_sessions_revoked": 1}
    assert first.get("/api/auth/me").status_code == 200  # la sesión que cambia sigue viva
    assert second.get("/api/auth/me").status_code == 401  # las demás se cierran

    fresh = TestClient(app)
    assert login(fresh, "a@example.com", PASSWORD).status_code == 401
    assert login(fresh, "a@example.com", NEW).status_code == 200
    assert "auth.password_change" in audit_actions(database)
    with database.connect() as db:
        details = db.execute(
            "SELECT details FROM audit_events WHERE action = 'auth.password_change'"
        ).fetchone()["details"]
    assert PASSWORD not in (details or "") and NEW not in (details or "")


def test_wrong_current_password_is_refused_and_rate_limited(
    logged_in: Callable[..., TestClient],
) -> None:
    user = logged_in("a@example.com")
    codes = [change(user, "no-es-la-actual", NEW).status_code for _ in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
    # Ni siquiera la correcta pasa mientras dura el bloqueo: no sirve para adivinar.
    assert change(user, PASSWORD, NEW).status_code == 429


@pytest.mark.parametrize(
    ("new", "status"),
    [("corta", 422), (PASSWORD, 400)],
)
def test_weak_or_unchanged_password_is_rejected(
    logged_in: Callable[..., TestClient], new: str, status: int
) -> None:
    user = logged_in("a@example.com")
    assert change(user, PASSWORD, new).status_code == status


def test_a_user_cannot_change_someone_elses_password(
    app: Any, logged_in: Callable[..., TestClient]
) -> None:
    logged_in("victima@example.com")
    attacker = logged_in("atacante@example.com")
    # Con la contraseña de la víctima (igual en el fixture) solo cambia la PROPIA cuenta.
    assert change(attacker, PASSWORD, NEW).status_code == 200
    assert login(TestClient(app), "victima@example.com", PASSWORD).status_code == 200
