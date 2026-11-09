"""AI Gateway: único punto por el que los productos llaman a modelos.

Implementa el mismo contrato que un proveedor (`ChatProvider`), de modo que los casos de uso
no saben si hablan con un modelo local, con Bedrock o con una cadena de respaldo.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass

from ai_gateway.errors import PolicyError, ProviderError, ProviderUnavailableError
from ai_gateway.policy import GatewayPolicy
from ai_gateway.providers.base import ChatProvider
from ai_gateway.schemas import CompletionRequest, CompletionResult, InferenceMetrics, StreamChunk
from ai_gateway.streaming import stream_completion
from ai_gateway.usage import ModelPrice, Status, UsageStore, estimate_cost

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


class Gateway:
    def __init__(
        self,
        providers: Mapping[str, ChatProvider],
        routes: list[Route],
        policy: GatewayPolicy | None = None,
        *,
        cloud: frozenset[str] = frozenset(),
        prices: Mapping[tuple[str, str], ModelPrice] | None = None,
        usage: UsageStore | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        policy = policy or GatewayPolicy()
        if not routes:
            raise ValueError("El gateway necesita al menos una ruta")
        missing = {r.provider for r in routes} - providers.keys()
        if missing:
            raise ValueError(f"Rutas a proveedores no registrados: {sorted(missing)}")
        uses_cloud = any(r.provider in cloud for r in routes)
        if uses_cloud and not policy.allow_cloud:
            raise ValueError("Hay rutas en la nube pero la política no las permite")
        if uses_cloud and (policy.cloud_monthly_budget_usd is None or usage is None):
            raise ValueError("Las rutas en la nube exigen presupuesto mensual y registro de uso")

        self._providers = providers
        self._routes = routes
        self._policy = policy
        self._cloud = cloud
        self._prices = prices or {}
        self._usage = usage
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._routes[0].provider

    @property
    def model(self) -> str:
        return self._routes[0].model

    async def health(self) -> bool:
        return await self._providers[self.name].health()

    async def aclose(self) -> None:
        """Cierra los clientes HTTP de los proveedores que los mantienen abiertos."""
        for provider in self._providers.values():
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    def _check_input(self, request: CompletionRequest) -> None:
        chars = sum(len(m.content) for m in request.messages)
        if chars > self._policy.max_input_chars:
            raise PolicyError("La entrada supera el límite permitido")

    def _routed(self, route: Route, request: CompletionRequest) -> CompletionRequest:
        policy = self._policy
        return request.model_copy(
            update={
                "model": route.model,
                "max_output_tokens": min(
                    request.max_output_tokens or policy.max_output_tokens,
                    policy.max_output_tokens,
                ),
                "timeout_seconds": request.timeout_seconds or policy.timeout_seconds,
            }
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Como `complete`, pero entregando fragmentos. Reintentos y rutas de respaldo solo valen
        mientras no se haya emitido contenido: una vez empezada la respuesta, un fallo se propaga.
        El uso se registra al terminar, fallar o cancelarse (cancelado = `ok` con error_kind)."""
        self._check_input(request)
        last_error: ProviderError | None = None
        for route in self._routes:
            denial = await self._denial(route)
            if denial is not None:
                await self._record(request, route, "denied", error_kind=denial)
                continue
            routed = self._routed(route, request)
            provider = self._providers[route.provider]
            for attempt in range(self._policy.max_retries + 1):
                started = time.perf_counter()
                emitted = False
                final: InferenceMetrics | None = None
                try:
                    async for chunk in stream_completion(provider, routed):
                        if chunk.done:
                            final = chunk.metrics
                        else:
                            emitted = True
                        yield chunk
                except ProviderError as exc:
                    latency = (time.perf_counter() - started) * 1000
                    await self._record(
                        request, route, "error", latency_ms=latency, error_kind=type(exc).__name__
                    )
                    if emitted:
                        raise
                    last_error = exc
                    if isinstance(exc, ProviderUnavailableError) and attempt < (
                        self._policy.max_retries
                    ):
                        await self._sleep(self._policy.retry_backoff_seconds * 2**attempt)
                        continue
                    break
                except (asyncio.CancelledError, GeneratorExit):
                    # El cliente se fue o pulsó Detener: la generación parcial también costó tiempo.
                    await asyncio.shield(
                        self._record_stream(request, route, started, final, "cancelled")
                    )
                    raise
                else:
                    await self._record_stream(request, route, started, final, None)
                    return
        if last_error is not None:
            raise last_error
        raise PolicyError("Ningún proveedor permitido por la política")

    async def _record_stream(
        self,
        request: CompletionRequest,
        route: Route,
        started: float,
        metrics: InferenceMetrics | None,
        error_kind: str | None,
    ) -> None:
        latency = (time.perf_counter() - started) * 1000
        result = CompletionResult(
            content="",
            model=route.model,
            provider=route.provider,
            input_tokens=metrics.prompt_tokens if metrics else None,
            output_tokens=metrics.tokens if metrics else None,
            latency_ms=metrics.total_ms if metrics and metrics.total_ms else latency,
            metrics=metrics,
        )
        await self._record(request, route, "ok", result=result, error_kind=error_kind)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        chars = sum(len(m.content) for m in request.messages)
        if chars > self._policy.max_input_chars:
            raise PolicyError("La entrada supera el límite permitido")

        last_error: ProviderError | None = None
        for route in self._routes:
            denial = await self._denial(route)
            if denial is not None:
                await self._record(request, route, "denied", error_kind=denial)
                continue
            try:
                return await self._attempt(route, request)
            except ProviderError as exc:
                last_error = exc  # se prueba la siguiente ruta (si la hay y está permitida)

        if last_error is not None:
            raise last_error
        raise PolicyError("Ningún proveedor permitido por la política")

    async def _denial(self, route: Route) -> str | None:
        if route.provider not in self._cloud:
            return None
        if not self._policy.allow_cloud:
            return "cloud_disabled"
        budget = self._policy.cloud_monthly_budget_usd
        if budget is not None and self._usage is not None:
            spent = await asyncio.to_thread(self._usage.month_cost_usd)
            if spent >= budget:
                return "budget_exceeded"
        return None

    async def _attempt(self, route: Route, request: CompletionRequest) -> CompletionResult:
        policy = self._policy
        routed = request.model_copy(
            update={
                "model": route.model,
                "max_output_tokens": min(
                    request.max_output_tokens or policy.max_output_tokens,
                    policy.max_output_tokens,
                ),
                "timeout_seconds": request.timeout_seconds or policy.timeout_seconds,
            }
        )
        provider = self._providers[route.provider]
        started = time.perf_counter()
        error: ProviderError | None = None

        for attempt in range(policy.max_retries + 1):
            try:
                result = await provider.complete(routed)
            except ProviderUnavailableError as exc:
                error = exc
                if attempt < policy.max_retries:
                    await self._sleep(policy.retry_backoff_seconds * 2**attempt)
                    continue
            except ProviderError as exc:
                error = exc
            else:
                await self._record(request, route, "ok", result=result)
                return result
            break

        assert error is not None
        latency = (time.perf_counter() - started) * 1000
        await self._record(
            request, route, "error", latency_ms=latency, error_kind=type(error).__name__
        )
        raise error

    def _cost(self, route: Route, result: CompletionResult | None) -> float | None:
        if route.provider not in self._cloud:
            return 0.0
        price = self._prices.get((route.provider, route.model))
        if price is None or result is None:
            return None
        return estimate_cost(price, result.input_tokens, result.output_tokens)

    async def _record(
        self,
        request: CompletionRequest,
        route: Route,
        status: Status,
        *,
        result: CompletionResult | None = None,
        latency_ms: float | None = None,
        error_kind: str | None = None,
    ) -> None:
        if self._usage is None:
            return
        try:
            await asyncio.to_thread(
                self._usage.record,
                user_id=request.user_id,
                organization_id=request.organization_id,
                api_key_id=request.api_key_id,
                provider=route.provider,
                model=route.model,
                status=status,
                input_tokens=result.input_tokens if result else None,
                output_tokens=result.output_tokens if result else None,
                latency_ms=result.latency_ms if result else latency_ms,
                metrics=result.metrics if result else None,
                cost_usd=self._cost(route, result) if status == "ok" else None,
                error_kind=error_kind,
            )
        except Exception:  # el registro de uso nunca debe tumbar una respuesta ya obtenida
            logger.exception("No se pudo registrar el uso del modelo")
