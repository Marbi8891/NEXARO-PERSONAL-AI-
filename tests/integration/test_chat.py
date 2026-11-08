from collections.abc import Callable

from fastapi.testclient import TestClient

from ai_gateway.errors import ProviderTimeoutError
from tests.conftest import HEADERS, FakeProvider


def post_chat(client: TestClient, message: str = "hola", conversation_id: str | None = None):
    body = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post("/api/chat", json=body, headers=HEADERS)


def test_chat_stores_both_turns_and_sends_system_prompt(
    client: TestClient, logged_in: Callable[..., TestClient], provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    reply = post_chat(alice, "hola NEXARO")

    assert reply.status_code == 200
    assert reply.json()["answer"] == "respuesta de prueba"

    sent = provider.requests[0]
    assert sent.messages[0].role == "system"
    assert "NEXARO Personal AI" in sent.messages[0].content
    assert sent.messages[-1].content == "hola NEXARO"

    conversation = alice.get(f"/api/conversations/{reply.json()['conversation_id']}").json()
    assert [m["role"] for m in conversation["messages"]] == ["user", "assistant"]


def test_history_is_sent_on_follow_up(
    client: TestClient, logged_in: Callable[..., TestClient], provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    first = post_chat(alice, "uno").json()["conversation_id"]
    post_chat(alice, "dos", first)

    roles = [m.role for m in provider.requests[1].messages]
    assert roles == ["system", "user", "assistant", "user"]


def test_conversation_list_has_title_and_preview(
    client: TestClient, logged_in: Callable[..., TestClient]
) -> None:
    alice = logged_in("alice@example.com")
    post_chat(alice, "primera pregunta")
    item = alice.get("/api/conversations").json()["conversations"][0]
    assert item["title"] == "primera pregunta"
    assert item["preview"] == "respuesta de prueba"
    assert item["message_count"] == 2


def test_conversation_id_length_is_bounded(
    client: TestClient, logged_in: Callable[..., TestClient]
) -> None:
    alice = logged_in("alice@example.com")
    assert post_chat(alice, "hola", "x" * 65).status_code == 422


def test_provider_failure_returns_generic_502(
    client: TestClient, logged_in: Callable[..., TestClient], provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    provider.error = ProviderTimeoutError("detalle interno http://ollama:11434")
    response = post_chat(alice)

    assert response.status_code == 502
    assert "ollama" not in response.text.lower()


def test_health_reports_provider_state_without_details(
    client: TestClient, provider: FakeProvider
) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    provider.healthy = False
    response = client.get("/api/health")
    assert response.status_code == 503
    assert "detail" in response.json() and "interno" not in response.text


def test_security_headers_are_present(client: TestClient) -> None:
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
