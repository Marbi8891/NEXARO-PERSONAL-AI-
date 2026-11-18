"""/api/health comprueba Ollama y el modelo configurado con una sola consulta (ADR-0021)."""

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from ai_gateway.errors import ProviderUnavailableError
from ai_gateway.gateway import Gateway, Route, model_installed
from ai_gateway.schemas import CompletionRequest, CompletionResult
from nexaro_api.main import create_app
from nexaro_core.config import Settings

MODEL = "qwen2.5:3b"


class ListingProvider:
    """Proveedor que, como Ollama, sabe qué modelos tiene instalados."""

    name = "ollama"

    def __init__(self, installed: list[str]) -> None:
        self.installed = installed
        self.down = False
        self.list_calls = 0
        self.health_calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content="ok", model=request.model, provider=self.name)

    async def health(self) -> bool:
        self.health_calls += 1
        return not self.down

    async def list_models(self) -> list[dict[str, Any]]:
        self.list_calls += 1
        if self.down:
            raise ProviderUnavailableError("caído")
        return [{"name": name} for name in self.installed]


def gateway(provider: ListingProvider) -> Gateway:
    return Gateway({"ollama": provider}, [Route("ollama", MODEL)])


def test_model_names_match_with_implicit_latest() -> None:
    assert model_installed("llama3.2", [{"name": "llama3.2:latest"}])
    assert model_installed(MODEL, [{"name": MODEL}])
    assert not model_installed(MODEL, [{"name": "qwen2.5:7b"}])


def test_readiness_uses_a_single_listing_call() -> None:
    provider = ListingProvider([MODEL])
    assert asyncio.run(gateway(provider).readiness()) == (True, True)
    assert (provider.list_calls, provider.health_calls) == (1, 0)

    provider.installed = []
    assert asyncio.run(gateway(provider).readiness()) == (True, False)

    provider.down = True
    assert asyncio.run(gateway(provider).readiness()) == (False, None)


def test_readiness_without_model_listing_falls_back_to_health() -> None:
    class Plain(ListingProvider):
        list_models = None  # type: ignore[assignment]

    provider = Plain([])
    assert asyncio.run(gateway(provider).readiness()) == (True, None)
    assert provider.health_calls == 1


def test_health_is_ready_when_ollama_answers_and_model_is_installed(settings: Settings) -> None:
    provider = ListingProvider([MODEL])
    with TestClient(create_app(settings, chat_provider=gateway(provider))) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ollama": "connected", "model": "ready"}


def test_health_is_503_without_the_model_and_does_not_reveal_its_name(
    settings: Settings,
) -> None:
    provider = ListingProvider(["otro:1b"])
    with TestClient(create_app(settings, chat_provider=gateway(provider))) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Modelo de IA no disponible"}
        assert "qwen" not in response.text

        provider.installed = [MODEL]  # tras `make model`, sin reiniciar
        assert client.get("/api/health").status_code == 200


def test_health_is_503_when_ollama_is_down(settings: Settings) -> None:
    provider = ListingProvider([MODEL])
    provider.down = True
    with TestClient(create_app(settings, chat_provider=gateway(provider))) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Servicio de IA no disponible"}
        assert client.get("/api/health/live").status_code == 200  # liveness no depende de Ollama


def test_providers_without_readiness_keep_working(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "ollama": "connected", "model": "unknown"}
