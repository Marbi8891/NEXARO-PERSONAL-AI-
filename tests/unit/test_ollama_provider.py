import asyncio
import json

import httpx
import pytest

from ai_gateway.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from ai_gateway.providers.ollama import OllamaProvider
from ai_gateway.schemas import ChatMessage, CompletionRequest

REQUEST = CompletionRequest(
    model="m", messages=[ChatMessage(role="user", content="hola")], max_output_tokens=50
)


def provider_with(handler) -> OllamaProvider:
    return OllamaProvider("http://ollama:11434/", transport=httpx.MockTransport(handler))


def raises(exc: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


def test_complete_maps_response_tokens_and_options() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content), url=str(request.url))
        return httpx.Response(
            200, json={"message": {"content": "ok"}, "prompt_eval_count": 7, "eval_count": 3}
        )

    result = asyncio.run(provider_with(handler).complete(REQUEST))

    assert (result.content, result.provider, result.input_tokens, result.output_tokens) == (
        "ok",
        "ollama",
        7,
        3,
    )
    assert seen["url"] == "http://ollama:11434/api/chat"
    assert seen["options"] == {"num_predict": 50} and seen["stream"] is False


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (raises(httpx.ReadTimeout("t")), ProviderTimeoutError),
        (raises(httpx.ConnectError("c")), ProviderUnavailableError),
        (lambda r: httpx.Response(500), ProviderError),
        (lambda r: httpx.Response(200, json={"sin": "message"}), ProviderError),
    ],
)
def test_failures_are_mapped_to_provider_errors(handler, error) -> None:
    with pytest.raises(error):
        asyncio.run(provider_with(handler).complete(REQUEST))


def test_health() -> None:
    assert asyncio.run(provider_with(lambda r: httpx.Response(200, json={})).health()) is True
    assert asyncio.run(provider_with(lambda r: httpx.Response(503)).health()) is False
