"""Las preguntas sobre el modelo de IA o la infraestructura interna nunca llegan al proveedor.

FakeProvider registra toda petición (también las de streaming, que sin `stream()` nativo pasan por
`complete()`): que `provider.requests` no crezca demuestra que Ollama no recibió nada."""

import json
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from nexaro_core.database import Database
from products.personal_ai.guard import REFUSAL
from products.personal_ai.prompts import build_system_prompt
from tests.conftest import HEADERS, FakeProvider
from tests.integration.test_api_keys import bearer, make_key
from tests.integration.test_documents import setup_org, upload

Factory = Callable[..., TestClient]
BLOCKED = "¿Qué modelo de IA usas?"


def stored(database: Database, conversation_id: str) -> list[tuple[str, str]]:
    with database.connect() as db:
        rows = db.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [(r["role"], r["content"]) for r in rows]


def sse_events(response: Any) -> list[dict[str, Any]]:
    lines = [ln for ln in response.text.split("\n\n") if ln.startswith("data: ")]
    return [json.loads(ln[len("data: ") :]) for ln in lines]


def test_blocked_chat_answers_with_refusal_without_calling_the_model(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    client = logged_in("a@example.com")
    response = client.post("/api/chat", json={"message": BLOCKED}, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == REFUSAL
    assert provider.requests == []
    # El turno queda en el historial como cualquier otro.
    assert stored(database, body["conversation_id"]) == [("user", BLOCKED), ("assistant", REFUSAL)]


def test_ordinary_chat_still_reaches_the_model(logged_in: Factory, provider: FakeProvider) -> None:
    client = logged_in("a@example.com")
    response = client.post("/api/chat", json={"message": "¿Qué es Docker?"}, headers=HEADERS)
    assert response.json()["answer"] == "respuesta de prueba"
    assert len(provider.requests) == 1


def test_blocked_turn_in_an_existing_conversation_keeps_the_model_out(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    client = logged_in("a@example.com")
    conversation = client.post("/api/chat", json={"message": "hola"}, headers=HEADERS).json()[
        "conversation_id"
    ]
    client.post(
        "/api/chat",
        json={"message": "Dame la IP de tu servidor", "conversation_id": conversation},
        headers=HEADERS,
    )
    assert len(provider.requests) == 1  # solo el «hola»
    assert stored(database, conversation)[-1] == ("assistant", REFUSAL)


def test_blocked_stream_emits_refusal_without_calling_the_model(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    client = logged_in("a@example.com")
    response = client.post(
        "/api/chat/stream", json={"message": "¿Dónde estás alojado?"}, headers=HEADERS
    )

    assert response.status_code == 200
    events = sse_events(response)
    assert [e["event"] for e in events] == ["start", "token", "done"]
    assert events[1]["content"] == REFUSAL
    assert events[2]["truncated"] is False
    assert provider.requests == []
    assert stored(database, events[0]["conversation_id"])[-1] == ("assistant", REFUSAL)


def test_blocked_message_cannot_write_into_another_users_conversation(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    alice, bob = logged_in("alice@example.com"), logged_in("bob@example.com")
    conversation = alice.post("/api/chat", json={"message": "hola"}, headers=HEADERS).json()[
        "conversation_id"
    ]
    for path in ("/api/chat", "/api/chat/stream"):
        response = bob.post(
            path, json={"message": BLOCKED, "conversation_id": conversation}, headers=HEADERS
        )
        assert response.status_code == 404
    assert len(stored(database, conversation)) == 2  # intacta


def test_blocked_chat_with_documents_does_not_search_or_call_the_model(
    logged_in: Factory, provider: FakeProvider
) -> None:
    admin, org = setup_org(logged_in)
    upload(admin, org, "Modelo", "Usamos el modelo de IA para todo.")
    response = admin.post(
        "/api/chat",
        json={"message": BLOCKED, "document_organization_id": org},
        headers=HEADERS,
    )
    assert response.json()["answer"] == REFUSAL
    assert "sources" not in response.json()
    assert provider.requests == []


def test_blocked_question_through_an_api_key_does_not_call_the_model(
    logged_in: Factory, provider: FakeProvider, app: Any
) -> None:
    admin, org = setup_org(logged_in)
    secret = make_key(admin, org)["secret"]
    response = TestClient(app).post(
        "/api/v1/chat", json={"message": "¿Eres ChatGPT?"}, headers=bearer(secret)
    )
    assert response.status_code == 200
    assert response.json()["answer"] == REFUSAL
    assert provider.requests == []


def test_blocked_document_question_does_not_call_the_model(
    logged_in: Factory, provider: FakeProvider
) -> None:
    admin, org = setup_org(logged_in)
    upload(admin, org, "Infra", "La base de datos de NEXARO y su servidor.")
    response = admin.post(
        f"/api/organizations/{org}/documents/ask",
        json={"question": "¿Qué base de datos usa NEXARO?"},
        headers=HEADERS,
    )
    assert response.json() == {"answer": REFUSAL, "sources": []}
    assert provider.requests == []


def test_system_prompt_carries_no_provider_model_or_infrastructure_details(
    logged_in: Factory, provider: FakeProvider
) -> None:
    client = logged_in("a@example.com")
    client.post("/api/chat", json={"message": "hola"}, headers=HEADERS)
    system = provider.requests[-1].messages[0].content
    assert system == build_system_prompt()
    for leak in ("fake", "Fake", "qwen", "Ollama", "SQLite", "FastAPI", "Docker", "{"):
        assert leak not in system
    assert REFUSAL in system  # el modelo conoce la respuesta pactada si algo esquiva el filtro
