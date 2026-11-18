"""Modo tutor: mismo flujo que el chat general, con sus reglas y respuestas acotadas."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from products.personal_ai.guard import REFUSAL
from products.personal_ai.prompts import TUTOR_RULES, build_system_prompt
from tests.conftest import HEADERS, FakeProvider
from tests.integration.test_api_keys import bearer, make_key
from tests.integration.test_documents import setup_org

Factory = Callable[..., TestClient]
CODE_QUESTION = "¿Cómo hago una función en Python que diga si un número es primo?"


def test_tutor_prompt_extends_the_general_one() -> None:
    general, tutor = build_system_prompt(), build_system_prompt("tutor")
    assert tutor == general + TUTOR_RULES
    assert "MODO TUTOR" not in general
    assert "no des la solución completa" in tutor


def test_default_mode_is_general(logged_in: Factory, provider: FakeProvider) -> None:
    client = logged_in("a@example.com")
    client.post("/api/chat", json={"message": CODE_QUESTION}, headers=HEADERS)
    request = provider.requests[-1]
    assert request.messages[0].content == build_system_prompt()
    assert request.max_output_tokens == 2048  # consulta de código en modo general


def test_tutor_mode_uses_tutor_prompt_and_never_the_long_output_cap(
    logged_in: Factory, provider: FakeProvider
) -> None:
    client = logged_in("a@example.com")
    response = client.post(
        "/api/chat", json={"message": CODE_QUESTION, "mode": "tutor"}, headers=HEADERS
    )
    assert response.status_code == 200
    request = provider.requests[-1]
    assert request.messages[0].content == build_system_prompt("tutor")
    assert request.max_output_tokens == 1024
    # Una consulta breve conserva su tope corto también en modo tutor.
    client.post("/api/chat", json={"message": "hola", "mode": "tutor"}, headers=HEADERS)
    assert provider.requests[-1].max_output_tokens == 512


def test_tutor_mode_in_streaming(logged_in: Factory, provider: FakeProvider) -> None:
    client = logged_in("a@example.com")
    response = client.post(
        "/api/chat/stream", json={"message": CODE_QUESTION, "mode": "tutor"}, headers=HEADERS
    )
    assert response.status_code == 200
    assert provider.requests[-1].messages[0].content == build_system_prompt("tutor")


def test_unknown_mode_is_rejected(logged_in: Factory, provider: FakeProvider) -> None:
    client = logged_in("a@example.com")
    for path in ("/api/chat", "/api/chat/stream"):
        response = client.post(path, json={"message": "hola", "mode": "root"}, headers=HEADERS)
        assert response.status_code == 422
    assert provider.requests == []


def test_tutor_mode_through_an_api_key(
    logged_in: Factory, provider: FakeProvider, app: Any
) -> None:
    admin, org = setup_org(logged_in)
    secret = make_key(admin, org)["secret"]
    response = TestClient(app).post(
        "/api/v1/chat", json={"message": CODE_QUESTION, "mode": "tutor"}, headers=bearer(secret)
    )
    assert response.status_code == 200
    assert provider.requests[-1].messages[0].content == build_system_prompt("tutor")


def test_restricted_questions_are_blocked_in_tutor_mode(
    logged_in: Factory, provider: FakeProvider
) -> None:
    client = logged_in("a@example.com")
    response = client.post(
        "/api/chat", json={"message": "¿Qué modelo de IA usas?", "mode": "tutor"}, headers=HEADERS
    )
    assert response.json()["answer"] == REFUSAL
    assert provider.requests == []
