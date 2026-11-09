import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ai_gateway.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from ai_gateway.schemas import CompletionRequest, CompletionResult, InferenceMetrics, StreamChunk

DEFAULT_TIMEOUT_SECONDS = 180.0
HEALTH_TIMEOUT_SECONDS = 8.0
CONNECT_TIMEOUT_SECONDS = 5.0
_NS_PER_MS = 1_000_000


def _ms(nanoseconds: object) -> float | None:
    return round(nanoseconds / _NS_PER_MS, 1) if isinstance(nanoseconds, int) else None


class OllamaProvider:
    """Cliente de Ollama. Un único `httpx.AsyncClient` con conexiones persistentes durante toda la
    vida de la aplicación (se cierra con `aclose()`), en lugar de uno por petición."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        *,
        default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        keep_alive: str | None = None,
        num_ctx: int | None = None,
        num_thread: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_timeout = default_timeout
        self._keep_alive = keep_alive
        self._num_ctx = num_ctx
        self._num_thread = num_thread
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(default_timeout, connect=CONNECT_TIMEOUT_SECONDS),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=300),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _payload(self, request: CompletionRequest, *, stream: bool) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        # num_ctx constante entre peticiones: si cambia, Ollama recarga el modelo.
        if self._num_ctx is not None:
            options["num_ctx"] = self._num_ctx
        if self._num_thread is not None:
            options["num_thread"] = self._num_thread
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": stream,
        }
        if options:
            payload["options"] = options
        if self._keep_alive is not None:
            payload["keep_alive"] = self._keep_alive
        return payload

    def _timeout(self, request: CompletionRequest) -> httpx.Timeout:
        return httpx.Timeout(
            request.timeout_seconds or self._default_timeout, connect=CONNECT_TIMEOUT_SECONDS
        )

    @staticmethod
    def _metrics(body: dict[str, Any], ttft_ms: float | None, total_ms: float) -> InferenceMetrics:
        return InferenceMetrics(
            ttft_ms=ttft_ms,
            load_ms=_ms(body.get("load_duration")),
            prompt_eval_ms=_ms(body.get("prompt_eval_duration")),
            generation_ms=_ms(body.get("eval_duration")),
            total_ms=round(total_ms, 1),
            prompt_tokens=body.get("prompt_eval_count"),
            tokens=body.get("eval_count"),
            done_reason=body.get("done_reason"),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        started = time.perf_counter()
        try:
            response = await self._http.post(
                f"{self._base_url}/api/chat",
                json=self._payload(request, stream=False),
                timeout=self._timeout(request),
            )
            response.raise_for_status()
            body = response.json()
            content = body["message"]["content"]
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama agotó el tiempo de espera") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("Ollama no está disponible") from exc
        except (httpx.HTTPStatusError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Respuesta no válida de Ollama") from exc

        total_ms = (time.perf_counter() - started) * 1000
        return CompletionResult(
            content=content,
            model=request.model,
            provider=self.name,
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
            latency_ms=total_ms,
            metrics=self._metrics(body, None, total_ms),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Streaming real (NDJSON de Ollama).

        Si el consumidor deja de iterar o se cancela, se cierra la conexión
        y Ollama detiene la generación.
        """
        started = time.perf_counter()
        ttft_ms: float | None = None
        try:
            async with self._http.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=self._payload(request, stream=True),
                timeout=self._timeout(request),
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError("Respuesta no válida de Ollama")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise ProviderError("Ollama devolvió un error durante la generación")
                    content = chunk.get("message", {}).get("content") or ""
                    if content:
                        if ttft_ms is None:
                            ttft_ms = round((time.perf_counter() - started) * 1000, 1)
                        yield StreamChunk(content=content)
                    if chunk.get("done"):
                        total_ms = (time.perf_counter() - started) * 1000
                        yield StreamChunk(
                            done=True, metrics=self._metrics(chunk, ttft_ms, total_ms)
                        )
                        return
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama agotó el tiempo de espera") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("Ollama no está disponible") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Respuesta no válida de Ollama") from exc
        raise ProviderError("Ollama cerró la conexión sin terminar la respuesta")

    async def list_models(self) -> list[dict[str, Any]]:
        """Modelos instalados en Ollama (`/api/tags`): nombre, tamaño, parámetros y cuantización."""
        try:
            response = await self._http.get(
                f"{self._base_url}/api/tags", timeout=HEALTH_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            items = response.json()["models"]
            return [
                {
                    "name": str(item["name"]),
                    "size_bytes": item.get("size"),
                    "parameter_size": (item.get("details") or {}).get("parameter_size"),
                    "quantization": (item.get("details") or {}).get("quantization_level"),
                }
                for item in items
            ]
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama agotó el tiempo de espera") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("Ollama no está disponible") from exc
        except (httpx.HTTPStatusError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Respuesta no válida de Ollama") from exc

    async def health(self) -> bool:
        try:
            response = await self._http.get(
                f"{self._base_url}/api/tags", timeout=HEALTH_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        return True
