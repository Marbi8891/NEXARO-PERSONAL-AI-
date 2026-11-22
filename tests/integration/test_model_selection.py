"""Selección de modelo de punta a punta: API, conversación persistente y gateway real
(con un proveedor de pruebas que lista modelos; no es una prueba contra Ollama real)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_gateway.gateway import Gateway, Route
from ai_gateway.policy import GatewayPolicy
from nexaro_api.main import create_app
from nexaro_core.config import Settings
from tests.conftest import HEADERS, FakeProvider

Factory = Callable[..., TestClient]
INSTALLED = ["qwen2.5:3b", "llama3.2:latest"]


class ListingFake(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.installed = list(INSTALLED)

    async def list_models(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "size_bytes": 1, "parameter_size": None, "quantization": None}
            for n in self.installed
        ]


@pytest.fixture
def provider() -> ListingFake:
    return ListingFake()


@pytest.fixture
def app(settings: Settings, provider: ListingFake) -> Any:
    gateway = Gateway({"fake": provider}, [Route("fake", "qwen2.5:3b")], GatewayPolicy())
    return create_app(settings, chat_provider=gateway)


def chat(client: TestClient, message: str, **extra: Any) -> Any:
    return client.post("/api/chat", json={"message": message, **extra}, headers=HEADERS)


def conversation(client: TestClient, conversation_id: str) -> dict[str, Any]:
    return client.get(f"/api/conversations/{conversation_id}").json()["conversation"]


def test_models_endpoint_lists_installed_models_for_any_user(
    client: TestClient, logged_in: Factory
) -> None:
    assert client.get("/api/models").status_code == 401
    alice = logged_in("alice@example.com")
    body = alice.get("/api/models").json()
    assert body["default_model"] == "qwen2.5:3b"
    assert body["selectable"] is True and body["available"] is True
    assert [m["name"] for m in body["models"]] == INSTALLED
    assert "base_url" not in json.dumps(body)  # sin detalles internos del proveedor


def test_chosen_model_is_used_and_remembered_by_the_conversation(
    logged_in: Factory, provider: ListingFake
) -> None:
    alice = logged_in("alice@example.com")
    first = chat(alice, "hola", model="llama3.2:latest").json()
    conversation_id = first["conversation_id"]
    assert provider.requests[-1].model == "llama3.2:latest"
    assert conversation(alice, conversation_id)["model"] == "llama3.2:latest"

    chat(alice, "sigue", conversation_id=conversation_id)  # sin `model`: el de la conversación
    assert provider.requests[-1].model == "llama3.2:latest"

    listed = alice.get("/api/conversations").json()["conversations"]
    assert listed[0]["model"] == "llama3.2:latest"


def test_auto_returns_the_conversation_to_the_configured_model(
    logged_in: Factory, provider: ListingFake
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "hola", model="llama3.2:latest").json()["conversation_id"]
    chat(alice, "vuelve", conversation_id=conversation_id, model="auto")
    assert provider.requests[-1].model == "qwen2.5:3b"
    assert conversation(alice, conversation_id)["model"] is None


def test_missing_model_is_a_clear_error_and_keeps_history(
    logged_in: Factory, provider: ListingFake
) -> None:
    alice = logged_in("alice@example.com")
    conversation_id = chat(alice, "hola").json()["conversation_id"]
    calls = len(provider.requests)

    failed = chat(alice, "otra", conversation_id=conversation_id, model="no-instalado")

    assert failed.status_code == 422
    assert "no-instalado" in failed.json()["detail"]
    assert len(provider.requests) == calls  # no se llamó a otro modelo en su lugar
    detail = alice.get(f"/api/conversations/{conversation_id}").json()
    assert [m["content"] for m in detail["messages"]] == ["hola", "respuesta de prueba"]
    assert detail["conversation"]["model"] is None  # un modelo que falla no queda fijado


def test_stream_reports_missing_model_without_saving_the_turn(logged_in: Factory) -> None:
    alice = logged_in("alice@example.com")
    response = alice.post(
        "/api/chat/stream", json={"message": "hola", "model": "no-instalado"}, headers=HEADERS
    )
    events = [json.loads(x[6:]) for x in response.text.split("\n\n") if x.startswith("data: ")]
    assert events[-1]["event"] == "error"
    assert "no-instalado" in events[-1]["message"]
    assert alice.get("/api/conversations").json()["conversations"] == []


@pytest.mark.parametrize("model", ["", "con espacio", "-empieza-mal", "x" * 201, "a;rm"])
def test_invalid_model_names_are_rejected(logged_in: Factory, model: str) -> None:
    alice = logged_in("alice@example.com")
    assert chat(alice, "hola", model=model).status_code == 422


def test_another_users_conversation_model_cannot_be_changed(logged_in: Factory) -> None:
    alice = logged_in("alice@example.com")
    bob = logged_in("bob@example.com")
    conversation_id = chat(alice, "hola", model="llama3.2:latest").json()["conversation_id"]
    stolen = chat(bob, "mío", conversation_id=conversation_id, model="qwen2.5:3b")
    assert stolen.status_code == 404
    assert conversation(alice, conversation_id)["model"] == "llama3.2:latest"
