import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ai_gateway.breaker import CircuitBreaker
from ai_gateway.errors import PolicyError, ProviderError, ProviderUnavailableError
from ai_gateway.gateway import Gateway, Route
from ai_gateway.policy import GatewayPolicy
from ai_gateway.schemas import ChatMessage, CompletionRequest, CompletionResult, StreamChunk
from ai_gateway.usage import UsageStore, init_usage_schema
from nexaro_core.database import Database


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_breaker_opens_after_threshold_and_probes_after_cooldown() -> None:
    clock = Clock()
    breaker = CircuitBreaker(2, 30.0, clock)
    breaker.failure()
    assert breaker.state == "closed" and breaker.allow()
    breaker.failure()
    assert breaker.state == "open" and not breaker.allow()

    clock.now += 31
    assert breaker.state == "half_open"
    assert breaker.allow()  # una sonda
    assert not breaker.allow()  # y la puerta vuelve a cerrarse hasta conocer su resultado

    breaker.success()
    assert breaker.state == "closed" and breaker.failures == 0


class Flaky:
    def __init__(
        self, name: str, *, down: bool, error: type[ProviderError] = ProviderUnavailableError
    ) -> None:
        self.name = name
        self.down = down
        self.error = error
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        if self.down:
            raise self.error("caído")
        return CompletionResult(content="ok", model=request.model, provider=self.name)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        if self.down:
            raise self.error("caído")
        yield StreamChunk(content="ok")
        yield StreamChunk(done=True)

    async def health(self) -> bool:
        return not self.down


async def no_sleep(_: float) -> None:
    return None


def make(*providers: Flaky, clock: Clock) -> Gateway:
    return Gateway(
        {p.name: p for p in providers},
        [Route(p.name, f"model-{p.name}") for p in providers],
        GatewayPolicy(max_retries=0, breaker_threshold=2, breaker_cooldown_seconds=30.0),
        sleep=no_sleep,
        clock=clock,
    )


REQUEST = CompletionRequest(model="x", messages=[ChatMessage(role="user", content="hola")])


def test_open_circuit_fails_fast_without_calling_the_provider() -> None:
    clock = Clock()
    only = Flaky("a", down=True)
    gateway = make(only, clock=clock)

    for _ in range(2):
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(gateway.complete(REQUEST))
    assert only.calls == 2

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(gateway.complete(REQUEST))
    assert only.calls == 2  # no se volvió a llamar

    only.down = False
    clock.now += 31
    assert asyncio.run(gateway.complete(REQUEST)).content == "ok"  # la sonda recupera el circuito
    assert asyncio.run(gateway.describe())[0]["circuit"] == "closed"


def test_open_circuit_falls_back_to_the_next_route() -> None:
    clock = Clock()
    first, second = Flaky("a", down=True), Flaky("b", down=False)
    gateway = make(first, second, clock=clock)

    assert asyncio.run(gateway.complete(REQUEST)).provider == "b"
    assert asyncio.run(gateway.complete(REQUEST)).provider == "b"
    before = first.calls
    assert asyncio.run(gateway.complete(REQUEST)).provider == "b"
    assert first.calls == before  # circuito abierto: ni se intenta


def test_streaming_also_trips_and_respects_the_circuit() -> None:
    clock = Clock()
    only = Flaky("a", down=True)
    gateway = make(only, clock=clock)

    async def drain() -> None:
        async for _ in gateway.stream(REQUEST):
            pass

    for _ in range(2):
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(drain())
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(drain())
    assert only.calls == 2


def test_describe_reports_health_and_circuit() -> None:
    clock = Clock()
    gateway = make(Flaky("a", down=True), clock=clock)
    for _ in range(2):
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(gateway.complete(REQUEST))

    row = asyncio.run(gateway.describe())[0]

    assert row["provider"] == "a" and row["model"] == "model-a"
    assert row["healthy"] is False and row["circuit"] == "open"
    assert row["consecutive_failures"] == 2 and row["installed_models"] is None


def usage_store(tmp_path: Path) -> UsageStore:
    database = Database(tmp_path / "usage.db")
    with database.connect() as db:
        init_usage_schema(db)
    return UsageStore(database)


def retrying(provider: Flaky, clock: Clock, *, threshold: int, usage: UsageStore) -> Gateway:
    return Gateway(
        {provider.name: provider},
        [Route(provider.name, "m")],
        GatewayPolicy(max_retries=1, breaker_threshold=threshold, breaker_cooldown_seconds=30.0),
        usage=usage,
        sleep=no_sleep,
        clock=clock,
    )


async def drain(gateway: Gateway) -> None:
    async for _ in gateway.stream(REQUEST):
        pass


def test_no_retry_when_the_failure_opens_the_circuit(tmp_path: Path) -> None:
    provider = Flaky("a", down=True)
    store = usage_store(tmp_path)
    gateway = retrying(provider, Clock(), threshold=1, usage=store)

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(gateway.complete(REQUEST))

    assert provider.calls == 1  # sin reintento
    assert [(r["status"], r["requests"]) for r in store.summary()] == [("error", 1)]


def test_no_stream_retry_when_the_failure_opens_the_circuit(tmp_path: Path) -> None:
    provider = Flaky("a", down=True)
    store = usage_store(tmp_path)
    gateway = retrying(provider, Clock(), threshold=1, usage=store)

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(drain(gateway))

    assert provider.calls == 1
    assert [(r["status"], r["requests"]) for r in store.summary()] == [("error", 1)]


@pytest.mark.parametrize("mode", ["complete", "stream"])
def test_retry_still_happens_while_the_circuit_stays_closed(tmp_path: Path, mode: str) -> None:
    provider = Flaky("a", down=True)
    gateway = retrying(provider, Clock(), threshold=5, usage=usage_store(tmp_path))

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(gateway.complete(REQUEST) if mode == "complete" else drain(gateway))

    assert provider.calls == 2


def test_other_provider_errors_are_not_retried_nor_counted(tmp_path: Path) -> None:
    provider = Flaky("a", down=True, error=ProviderError)
    gateway = retrying(provider, Clock(), threshold=1, usage=usage_store(tmp_path))

    with pytest.raises(ProviderError):
        asyncio.run(gateway.complete(REQUEST))

    assert provider.calls == 1
    assert asyncio.run(gateway.describe())[0]["circuit"] == "closed"


def test_exhausted_cloud_budget_does_not_spend_the_half_open_probe(tmp_path: Path) -> None:
    clock = Clock()
    cloud = Flaky("bedrock", down=True)
    store = usage_store(tmp_path)
    gateway = Gateway(
        {"bedrock": cloud},
        [Route("bedrock", "m")],
        GatewayPolicy(
            max_retries=0,
            breaker_threshold=2,
            breaker_cooldown_seconds=30.0,
            allow_cloud=True,
            cloud_monthly_budget_usd=1.0,
        ),
        cloud=frozenset({"bedrock"}),
        usage=store,
        sleep=no_sleep,
        clock=clock,
    )
    for _ in range(2):
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(gateway.complete(REQUEST))
    assert asyncio.run(gateway.describe())[0]["circuit"] == "open"

    store.record(user_id=None, provider="bedrock", model="m", status="ok", cost_usd=2.0)
    clock.now += 31
    assert asyncio.run(gateway.describe())[0]["circuit"] == "half_open"

    with pytest.raises(PolicyError):  # presupuesto agotado
        asyncio.run(gateway.complete(REQUEST))

    assert cloud.calls == 2
    assert asyncio.run(gateway.describe())[0]["circuit"] == "half_open"  # la sonda sigue intacta
