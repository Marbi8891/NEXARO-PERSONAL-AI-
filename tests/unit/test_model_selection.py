"""Selección de modelo en el gateway: descubrimiento y sin cambio silencioso de modelo."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from ai_gateway.errors import ModelNotAvailableError, ProviderUnavailableError
from ai_gateway.gateway import Gateway, Route
from ai_gateway.policy import GatewayPolicy
from ai_gateway.schemas import ChatMessage, CompletionRequest, CompletionResult, StreamChunk
from ai_gateway.usage import UsageStore, init_usage_schema
from nexaro_core.database import Database


class ListingProvider:
    """Doble de un proveedor que lista modelos (como Ollama). Nunca sale a la red."""

    def __init__(self, name: str, installed: list[str], *errors: Exception) -> None:
        self.name = name
        self.installed = installed
        self.errors = list(errors)
        self.requests: list[CompletionRequest] = []
        self.listing_error: Exception | None = None

    async def list_models(self) -> list[dict[str, Any]]:
        if self.listing_error is not None:
            raise self.listing_error
        return [{"name": n, "size_bytes": 1, "parameter_size": "3B"} for n in self.installed]

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if self.errors:
            raise self.errors.pop(0)
        return CompletionResult(content="ok", model=request.model, provider=self.name)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        self.requests.append(request)
        yield StreamChunk(content="ok")
        yield StreamChunk(done=True)

    async def health(self) -> bool:
        return True


class NoListProvider(ListingProvider):
    list_models = None  # type: ignore[assignment]  # p. ej. Bedrock: no sabe listar


async def no_sleep(_: float) -> None:
    return None


def request(override: str | None = None) -> CompletionRequest:
    return CompletionRequest(
        model="ignored",
        messages=[ChatMessage(role="user", content="hola")],
        model_override=override,
    )


@pytest.fixture
def store(tmp_path: Path) -> UsageStore:
    database = Database(tmp_path / "usage.db")
    with database.connect() as db:
        init_usage_schema(db)
    return UsageStore(database)


def gateway(*providers: ListingProvider, store: UsageStore | None = None) -> Gateway:
    return Gateway(
        {p.name: p for p in providers},
        [Route(p.name, f"default-{p.name}") for p in providers],
        GatewayPolicy(max_retries=0),
        usage=store,
        sleep=no_sleep,
    )


def test_available_models_are_discovered_from_the_provider() -> None:
    local = ListingProvider("local", ["qwen2.5:3b", "llama3.2:latest"])
    second = ListingProvider("other", [])
    info = asyncio.run(gateway(local, second).available_models())
    assert info["provider"] == "local"
    assert info["default_model"] == "default-local"
    assert info["selectable"] is True
    assert info["available"] is True
    assert info["default_installed"] is False  # «default-local» no está instalado
    assert info["fallback"] == ["other"]
    assert [m["name"] for m in info["models"]] == ["qwen2.5:3b", "llama3.2:latest"]


def test_available_models_reports_a_down_provider_without_inventing_models() -> None:
    local = ListingProvider("local", ["qwen2.5:3b"])
    local.listing_error = ProviderUnavailableError("caído")
    info = asyncio.run(gateway(local).available_models())
    assert info["available"] is False
    assert info["models"] == []


def test_chosen_model_is_the_one_sent_to_the_provider(store: UsageStore) -> None:
    local = ListingProvider("local", ["qwen2.5:3b", "llama3.2:latest"])
    result = asyncio.run(gateway(local, store=store).complete(request("llama3.2")))
    assert local.requests[0].model == "llama3.2"  # «llama3.2» == «llama3.2:latest»
    assert result.model == "llama3.2"
    assert [r["model"] for r in store.summary()] == ["llama3.2"]  # el uso registra el real


def test_without_choice_the_configured_model_is_used() -> None:
    local = ListingProvider("local", ["default-local"])
    asyncio.run(gateway(local).complete(request()))
    assert local.requests[0].model == "default-local"


def test_missing_model_fails_clearly_and_never_calls_the_provider() -> None:
    local = ListingProvider("local", ["qwen2.5:3b"])
    second = ListingProvider("other", ["no-existe"])
    gw = gateway(local, second)
    with pytest.raises(ModelNotAvailableError, match="no-existe"):
        asyncio.run(gw.complete(request("no-existe")))
    assert local.requests == []
    assert second.requests == []  # no se cambia de proveedor ni de modelo en silencio


def test_chosen_model_has_no_silent_fallback_when_it_fails() -> None:
    local = ListingProvider("local", ["qwen2.5:3b"], ProviderUnavailableError("caído"))
    second = ListingProvider("other", ["qwen2.5:3b"])
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(gateway(local, second).complete(request("qwen2.5:3b")))
    assert second.requests == []


def test_automatic_mode_keeps_the_configured_fallback() -> None:
    local = ListingProvider("local", [], ProviderUnavailableError("caído"))
    second = ListingProvider("other", [])
    result = asyncio.run(gateway(local, second).complete(request()))
    assert result.provider == "other"


def test_streaming_uses_the_chosen_model_and_checks_it_first() -> None:
    local = ListingProvider("local", ["phi3:mini"])
    gw = gateway(local)

    async def collect(req: CompletionRequest) -> list[StreamChunk]:
        return [chunk async for chunk in gw.stream(req)]

    asyncio.run(collect(request("phi3:mini")))
    assert local.requests[-1].model == "phi3:mini"
    with pytest.raises(ModelNotAvailableError):
        asyncio.run(collect(request("otro")))


def test_provider_that_cannot_list_models_rejects_a_choice() -> None:
    remote = NoListProvider("remote", [])
    gw = gateway(remote)
    info = asyncio.run(gw.available_models())
    assert info["selectable"] is False
    with pytest.raises(ModelNotAvailableError, match="no permite elegir"):
        asyncio.run(gw.complete(request("lo-que-sea")))
