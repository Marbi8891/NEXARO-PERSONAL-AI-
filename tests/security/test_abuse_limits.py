"""Abuso de recursos: ritmo y concurrencia del modelo, cuerpo, login tras NAT y cabeceras."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.security import ConcurrencyGuard, TooBusy
from tests.conftest import HEADERS, PASSWORD, FakeProvider, login


def make_client(
    settings: Settings, provider: FakeProvider, **overrides: Any
) -> Iterator[TestClient]:
    with TestClient(create_app(settings.model_copy(update=overrides), chat_provider=provider)) as c:
        yield c


def signed_in(
    client: TestClient, add_user: Callable[..., str], email: str = "a@example.com"
) -> None:
    add_user(email)
    assert login(client, email).status_code == 200


def chat(client: TestClient, text: str = "hola") -> Any:
    return client.post("/api/chat", json={"message": text}, headers=HEADERS)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_guard_limits_per_key_and_globally_and_release_is_idempotent() -> None:
    guard = ConcurrencyGuard(max_global=2, max_per_key=1, ttl_seconds=60)
    first = guard.acquire("a")
    with pytest.raises(TooBusy) as per_key:
        guard.acquire("a")
    assert per_key.value.scope == "user"
    guard.acquire("b")
    with pytest.raises(TooBusy) as total:
        guard.acquire("c")
    assert total.value.scope == "global"
    first.release()
    first.release()  # no libera un hueco ajeno
    assert guard.active() == 1
    guard.acquire("c")


def test_guard_leases_expire_so_a_cancelled_request_cannot_hold_a_slot() -> None:
    clock = Clock()
    guard = ConcurrencyGuard(1, 1, ttl_seconds=10, clock=clock)
    guard.acquire("a")
    with pytest.raises(TooBusy):
        guard.acquire("b")
    clock.now = 11
    guard.acquire("b")


def test_chat_is_rate_limited_per_user_and_does_not_affect_others(
    settings: Settings, add_user: Callable[..., str]
) -> None:
    provider = FakeProvider()
    app = create_app(
        settings.model_copy(update={"chat_requests_per_minute": 3}), chat_provider=provider
    )
    with TestClient(app) as alice, TestClient(app) as bob:
        signed_in(alice, add_user, "alice@example.com")
        signed_in(bob, add_user, "bob@example.com")
        assert [chat(alice).status_code for _ in range(3)] == [200, 200, 200]
        blocked = chat(alice)
        assert blocked.status_code == 429 and blocked.headers["retry-after"] == "30"
        assert (
            alice.post("/api/chat/stream", json={"message": "x"}, headers=HEADERS).status_code
            == 429
        )
        assert chat(bob).status_code == 200
    assert len(provider.requests) == 4  # los rechazados no llegaron al modelo


def test_busy_model_is_503_and_user_overload_is_429_before_calling_the_model(
    settings: Settings, add_user: Callable[..., str]
) -> None:
    provider = FakeProvider()
    app = create_app(settings.model_copy(update={"chat_max_concurrent": 1}), chat_provider=provider)
    with TestClient(app) as client:
        signed_in(client, add_user)
        lease = app.state.ctx.chat_guard.acquire("otro")
        busy = chat(client)
        assert busy.status_code == 503 and "ocupado" in busy.json()["detail"]
        assert "retry-after" in busy.headers
        lease.release()

        own = app.state.ctx.chat_guard.acquire(
            f"user:{client.get('/api/auth/me').json()['user']['id']}"
        )
        assert chat(client).status_code == 503  # global=1 ya ocupado por la propia
        own.release()
        assert chat(client).status_code == 200
    assert len(provider.requests) == 1


def test_leases_are_released_after_success_error_and_stream(
    settings: Settings, add_user: Callable[..., str]
) -> None:
    provider = FakeProvider()
    app = create_app(settings, chat_provider=provider)
    with TestClient(app) as client:
        signed_in(client, add_user)
        assert chat(client).status_code == 200
        provider.error = RuntimeError("boom")
        provider.error = None
        stream = client.post("/api/chat/stream", json={"message": "hola"}, headers=HEADERS)
        assert stream.status_code == 200
        other = client.post(
            "/api/chat", json={"message": "x", "conversation_id": "no"}, headers=HEADERS
        )
        assert other.status_code == 200
        assert app.state.ctx.chat_guard.active() == 0


def test_oversized_body_is_rejected_before_parsing(
    settings: Settings, add_user: Callable[..., str]
) -> None:
    provider = FakeProvider()
    app = create_app(settings.model_copy(update={"max_body_bytes": 1000}), chat_provider=provider)
    with TestClient(app) as client:
        signed_in(client, add_user)
        big = client.post(
            "/api/chat",
            content=b'{"message":"' + b"a" * 5000 + b'"}',
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        assert big.status_code == 413 and big.json() == {"detail": "Solicitud demasiado grande"}

        def chunks() -> Iterator[bytes]:  # sin Content-Length (chunked)
            for _ in range(10):
                yield b"a" * 500

        streamed = client.post(
            "/api/chat", content=chunks(), headers={**HEADERS, "Content-Type": "application/json"}
        )
        assert streamed.status_code == 413
        assert chat(client).status_code == 200  # el servidor sigue sirviendo
    assert provider.requests and len(provider.requests) == 1


def test_one_ip_failing_logins_does_not_lock_everyone_when_ip_threshold_is_raised(
    settings: Settings, add_user: Callable[..., str]
) -> None:
    provider = FakeProvider()
    tuned = settings.model_copy(update={"login_ip_max_attempts": 50})
    with TestClient(create_app(tuned, chat_provider=provider)) as client:
        add_user("valid@example.com")
        add_user("victim@example.com")
        for index in range(settings.login_max_attempts + 3):
            login(client, f"intruso{index}@example.com", "mala-clave-1234")
        assert login(client, "valid@example.com").status_code == 200  # misma IP, otra cuenta
        for _ in range(settings.login_max_attempts):
            login(client, "victim@example.com", "mala-clave-1234")
        assert (
            login(client, "victim@example.com", PASSWORD).status_code == 429
        )  # la cuenta sí se bloquea


def test_security_headers_and_no_store_on_api(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.headers["permissions-policy"].startswith("camera=()")
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers  # HTTP local: sin HSTS


def test_hsts_only_over_https_deployments(settings: Settings) -> None:
    secure = settings.model_copy(update={"cookie_secure": True})
    with TestClient(create_app(secure, chat_provider=FakeProvider())) as client:
        assert (
            "max-age=31536000"
            in client.get("/api/health/live").headers["strict-transport-security"]
        )


def test_api_docs_can_be_closed_explicitly_and_default_to_development_only(
    settings: Settings,
) -> None:
    provider = FakeProvider()
    for overrides, expected in (({}, 200), ({"api_docs": False}, 404)):
        app = create_app(settings.model_copy(update=overrides), chat_provider=provider)
        with TestClient(app) as client:
            assert client.get("/openapi.json").status_code == expected
    prod = settings.model_copy(
        update={
            "environment": "production",
            "cookie_secure": True,
            "allowed_origins": frozenset({"https://x.example"}),
            "api_docs": True,
        }
    )
    with TestClient(create_app(prod, chat_provider=provider)) as client:
        assert client.get("/openapi.json").status_code == 404  # producción nunca


def test_health_probe_is_cached_when_configured(settings: Settings) -> None:
    provider = FakeProvider()
    app = create_app(
        settings.model_copy(update={"health_cache_seconds": 60}), chat_provider=provider
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        provider.healthy = False
        assert client.get("/api/health").status_code == 200  # no vuelve a sondear a Ollama
