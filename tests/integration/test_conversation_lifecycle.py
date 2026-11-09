"""Borrado de conversaciones, turnos fallidos y límites del chat sin streaming."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_gateway.errors import ProviderError
from nexaro_core.config import Settings
from nexaro_core.database import Database
from tests.conftest import HEADERS, ORIGIN, FakeProvider, audit_actions, login

Factory = Callable[..., TestClient]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "nexaro.db",
        frontend_path=tmp_path / "sin-frontend",
        allowed_origins=frozenset({ORIGIN}),
        chat_history_max_chars=60,
        chat_max_concurrent_per_user=1,
        chat_requests_per_minute=3,
    )


def chat(client: TestClient, message: str, conversation_id: str | None = None):
    body: dict[str, str] = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post("/api/chat", json=body, headers=HEADERS)


def stream_events(client: TestClient, message: str, conversation_id: str | None = None):
    body: dict[str, str] = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = client.post("/api/chat/stream", json=body, headers=HEADERS)
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.split("\n\n") if line.startswith("data: ")
    ]


def conversation_ids(client: TestClient) -> list[str]:
    return [c["id"] for c in client.get("/api/conversations").json()["conversations"]]


def test_user_can_delete_own_conversation_with_audit(
    logged_in: Factory, database: Database
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "hola").json()["conversation_id"]

    deleted = alice.delete(f"/api/conversations/{conversation_id}", headers=HEADERS)

    assert deleted.status_code == 204
    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert conversation_ids(alice) == []
    with database.connect() as db:
        left = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert left == 0
    assert "conversation.delete" in audit_actions(database)
    assert alice.delete(f"/api/conversations/{conversation_id}", headers=HEADERS).status_code == 404


def test_cannot_delete_someone_elses_conversation(logged_in: Factory) -> None:
    alice = logged_in("alice@example.com")
    bob = logged_in("bob@example.com")
    conversation_id = chat(alice, "secreto de alice").json()["conversation_id"]

    assert bob.delete(f"/api/conversations/{conversation_id}", headers=HEADERS).status_code == 404

    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 200


def test_delete_needs_session_and_allowed_origin(client: TestClient, logged_in: Factory) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "hola").json()["conversation_id"]

    assert (
        client.delete(f"/api/conversations/{conversation_id}", headers=HEADERS).status_code == 401
    )
    wrong = {"Origin": "http://evil.example"}
    assert alice.delete(f"/api/conversations/{conversation_id}", headers=wrong).status_code == 403
    assert alice.delete(f"/api/conversations/{conversation_id}").status_code == 403
    assert conversation_ids(alice) == [conversation_id]


def test_failed_first_turn_leaves_no_trace(logged_in: Factory, provider: FakeProvider) -> None:
    alice = logged_in("alice@example.com")
    provider.error = ProviderError("caído")

    assert chat(alice, "hola").status_code == 502

    assert conversation_ids(alice) == []


def test_failed_turn_keeps_earlier_turns_without_orphan_message(
    logged_in: Factory, provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "uno").json()["conversation_id"]
    provider.error = ProviderError("caído")

    assert chat(alice, "dos", conversation_id).status_code == 502

    messages = alice.get(f"/api/conversations/{conversation_id}").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "uno"),
        ("assistant", "respuesta de prueba"),
    ]


def test_failed_stream_before_any_token_leaves_no_orphan(
    logged_in: Factory, provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "uno").json()["conversation_id"]
    provider.error = ProviderError("caído")

    events = stream_events(alice, "dos", conversation_id)
    assert events[-1]["event"] == "error"
    new_events = stream_events(alice, "tres")
    assert new_events[-1]["event"] == "error"

    assert conversation_ids(alice) == [conversation_id]
    messages = alice.get(f"/api/conversations/{conversation_id}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_non_streaming_chat_uses_the_same_limits_as_streaming(
    logged_in: Factory, provider: FakeProvider, settings: Settings
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "u" * 40).json()["conversation_id"]
    assert provider.requests[-1].max_output_tokens == settings.output_tokens_short
    chat(alice, "d" * 40, conversation_id)
    chat(alice, "t" * 40, conversation_id)

    sent = provider.requests[-1].messages
    # Presupuesto de 60 caracteres: solo caben el último intercambio (40 + 19) y el mensaje nuevo.
    assert [m.role for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1].content == "d" * 40


def user_key(client: TestClient) -> str:
    return f"user:{client.get('/api/auth/me').json()['user']['id']}"


def test_delete_is_refused_while_a_generation_is_active_and_allowed_after(
    logged_in: Factory, app: Any
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "hola").json()["conversation_id"]
    guard = app.state.ctx.chat_guard

    generation = guard.acquire(user_key(alice))  # una generación en curso del mismo usuario
    refused = alice.delete(f"/api/conversations/{conversation_id}", headers=HEADERS)
    assert refused.status_code == 429
    assert conversation_ids(alice) == [conversation_id]
    assert guard.active() == 1  # el rechazo no retiene ningún hueco

    generation.release()
    assert alice.delete(f"/api/conversations/{conversation_id}", headers=HEADERS).status_code == 204
    assert guard.active() == 0


def test_delete_does_not_spend_the_chat_rate_limit(logged_in: Factory) -> None:
    alice = logged_in("alice@example.com")
    ids = [chat(alice, f"mensaje {i}").json()["conversation_id"] for i in range(3)]
    assert chat(alice, "otro").status_code == 429  # ritmo agotado

    for conversation_id in ids:
        response = alice.delete(f"/api/conversations/{conversation_id}", headers=HEADERS)
        assert response.status_code == 204


def test_lease_is_released_on_404(logged_in: Factory, app: Any) -> None:
    alice = logged_in("alice@example.com")

    assert alice.delete("/api/conversations/no-existe", headers=HEADERS).status_code == 404

    assert app.state.ctx.chat_guard.active() == 0


def test_lease_is_released_when_the_delete_fails(
    logged_in: Factory, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged_in("alice@example.com")
    crashing = TestClient(app, raise_server_exceptions=False)
    assert login(crashing, "alice@example.com").status_code == 200

    def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(app.state.ctx.personal_ai, "delete_conversation", boom)

    assert crashing.delete("/api/conversations/x", headers=HEADERS).status_code == 500

    assert app.state.ctx.chat_guard.active() == 0
