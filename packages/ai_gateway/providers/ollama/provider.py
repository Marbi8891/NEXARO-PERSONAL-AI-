import time

import httpx

from ai_gateway.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from ai_gateway.schemas import CompletionRequest, CompletionResult

DEFAULT_TIMEOUT_SECONDS = 180.0
HEALTH_TIMEOUT_SECONDS = 8.0


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        *,
        default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_timeout = default_timeout
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
        }
        if request.max_output_tokens is not None:
            payload["options"] = {"num_predict": request.max_output_tokens}

        timeout = request.timeout_seconds or self._default_timeout
        started = time.perf_counter()

        try:
            async with self._client(timeout) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
                content = body["message"]["content"]
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama agotó el tiempo de espera") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("Ollama no está disponible") from exc
        except (httpx.HTTPStatusError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Respuesta no válida de Ollama") from exc

        return CompletionResult(
            content=content,
            model=request.model,
            provider=self.name,
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def health(self) -> bool:
        try:
            async with self._client(HEALTH_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError:
            return False
        return True
