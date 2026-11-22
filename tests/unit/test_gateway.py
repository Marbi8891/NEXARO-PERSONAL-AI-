import asyncio
from pathlib import Path

import pytest

from ai_gateway.errors import (
    PolicyError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from ai_gateway.gateway import Gateway, Route
from ai_gateway.policy import GatewayPolicy
from ai_gateway.schemas import ChatMessage, CompletionRequest, CompletionResult
from ai_gateway.usage import ModelPrice, UsageStore, init_usage_schema
from nexaro_core.database import Database


class StubProvider:
    def __init__(
        self, name: str, *errors: Exception, tokens: tuple[int, int] = (1000, 500)
    ) -> None:
        self.name = name
        self.errors = list(errors)
        self.tokens = tokens
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if self.errors:
            raise self.errors.pop(0)
        return CompletionResult(
            content="ok",
            model=request.model,
            provider=self.name,
            input_tokens=self.tokens[0],
            output_tokens=self.tokens[1],
            latency_ms=5.0,
        )

    async def health(self) -> bool:
        return True


async def no_sleep(_: float) -> None:
    return None


def request(text: str = "hola", **extra: object) -> CompletionRequest:
    return CompletionRequest(
        model="ignored", messages=[ChatMessage(role="user", content=text)], user_id="u1", **extra
    )


@pytest.fixture
def store(tmp_path: Path) -> UsageStore:
    database = Database(tmp_path / "usage.db")
    with database.connect() as db:
        init_usage_schema(db)
    return UsageStore(database)


def rows(store: UsageStore) -> list[dict]:
    return store.summary()


def run(gateway: Gateway, req: CompletionRequest) -> CompletionResult:
    return asyncio.run(gateway.complete(req))


def local_gateway(
    provider: StubProvider, store: UsageStore | None = None, **policy: object
) -> Gateway:
    return Gateway(
        {"local": provider},
        [Route("local", "m1")],
        GatewayPolicy(**policy),  # type: ignore[arg-type]
        usage=store,
        sleep=no_sleep,
    )


def test_route_model_and_output_cap_override_the_request() -> None:
    provider = StubProvider("local")
    run(local_gateway(provider, max_output_tokens=100), request(max_output_tokens=5000))
    sent = provider.requests[0]
    assert (sent.model, sent.max_output_tokens, sent.timeout_seconds) == ("m1", 100, 180.0)


def test_smaller_requested_output_is_respected() -> None:
    provider = StubProvider("local")
    run(local_gateway(provider, max_output_tokens=100), request(max_output_tokens=10))
    assert provider.requests[0].max_output_tokens == 10


def test_oversized_input_is_rejected_before_calling_the_provider() -> None:
    provider = StubProvider("local")
    with pytest.raises(PolicyError):
        run(local_gateway(provider, max_input_chars=10), request("x" * 11))
    assert provider.requests == []


def test_unavailable_is_retried_then_succeeds() -> None:
    provider = StubProvider("local", ProviderUnavailableError("caído"))
    assert run(local_gateway(provider, max_retries=1), request()).content == "ok"
    assert len(provider.requests) == 2


def test_timeout_is_not_retried() -> None:
    provider = StubProvider("local", ProviderTimeoutError("lento"))
    with pytest.raises(ProviderTimeoutError):
        run(local_gateway(provider, max_retries=3), request())
    assert len(provider.requests) == 1


def test_retries_are_bounded() -> None:
    provider = StubProvider("local", *[ProviderUnavailableError("x")] * 5)
    with pytest.raises(ProviderUnavailableError):
        run(local_gateway(provider, max_retries=2), request())
    assert len(provider.requests) == 3


def test_falls_back_to_next_local_route() -> None:
    primary = StubProvider("a", ProviderError("mal"))
    backup = StubProvider("b")
    gateway = Gateway(
        {"a": primary, "b": backup},
        [Route("a", "m-a"), Route("b", "m-b")],
        GatewayPolicy(max_retries=0),
        sleep=no_sleep,
    )
    result = run(gateway, request())
    assert (result.provider, backup.requests[0].model) == ("b", "m-b")


def test_cloud_routes_require_explicit_policy_budget_and_usage(store: UsageStore) -> None:
    cloud = StubProvider("cloud")
    routes = [Route("cloud", "c")]
    with pytest.raises(ValueError, match="no las permite"):
        Gateway({"cloud": cloud}, routes, GatewayPolicy(), cloud=frozenset({"cloud"}))
    with pytest.raises(ValueError, match="presupuesto"):
        Gateway(
            {"cloud": cloud}, routes, GatewayPolicy(allow_cloud=True), cloud=frozenset({"cloud"})
        )


def test_cost_is_computed_for_cloud_and_zero_for_local(store: UsageStore) -> None:
    local, cloud = StubProvider("local"), StubProvider("cloud", tokens=(2000, 1000))
    gateway = Gateway(
        {"local": local, "cloud": cloud},
        [Route("cloud", "c1"), Route("local", "m1")],
        GatewayPolicy(allow_cloud=True, cloud_monthly_budget_usd=10),
        cloud=frozenset({"cloud"}),
        prices={("cloud", "c1"): ModelPrice(input_per_1k=0.003, output_per_1k=0.015)},
        usage=store,
    )
    run(gateway, request())
    [row] = rows(store)
    assert (row["provider"], row["status"], row["input_tokens"]) == ("cloud", "ok", 2000)
    assert row["cost_usd"] == pytest.approx(0.021)
    assert store.month_cost_usd() == pytest.approx(0.021)


def test_exhausted_budget_skips_cloud_and_uses_local_fallback(store: UsageStore) -> None:
    local, cloud = StubProvider("local"), StubProvider("cloud")
    store.record(user_id=None, provider="cloud", model="c1", status="ok", cost_usd=5.0)
    gateway = Gateway(
        {"local": local, "cloud": cloud},
        [Route("cloud", "c1"), Route("local", "m1")],
        GatewayPolicy(allow_cloud=True, cloud_monthly_budget_usd=5.0),
        cloud=frozenset({"cloud"}),
        usage=store,
    )
    assert run(gateway, request()).provider == "local"
    assert cloud.requests == []
    statuses = {(r["provider"], r["status"]) for r in rows(store)}
    assert ("cloud", "denied") in statuses and ("local", "ok") in statuses


def test_only_cloud_route_with_exhausted_budget_raises_policy_error(store: UsageStore) -> None:
    store.record(user_id=None, provider="cloud", model="c1", status="ok", cost_usd=9.0)
    gateway = Gateway(
        {"cloud": StubProvider("cloud")},
        [Route("cloud", "c1")],
        GatewayPolicy(allow_cloud=True, cloud_monthly_budget_usd=5.0),
        cloud=frozenset({"cloud"}),
        usage=store,
    )
    with pytest.raises(PolicyError):
        run(gateway, request())


def test_usage_records_errors_without_message_content(store: UsageStore) -> None:
    provider = StubProvider("local", ProviderError("detalle interno secreto"))
    with pytest.raises(ProviderError):
        run(local_gateway(provider, store, max_retries=0), request("contenido privado"))
    with store._database.connect() as db:
        dump = " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM model_usage"))
    assert "ProviderError" in dump
    assert "contenido privado" not in dump and "secreto" not in dump


def test_usage_failure_never_breaks_the_response() -> None:
    class BrokenStore(UsageStore):
        def __init__(self) -> None:
            pass

        def record(self, **_: object) -> None:
            raise RuntimeError("disco lleno")

    gateway = Gateway({"local": StubProvider("local")}, [Route("local", "m")], usage=BrokenStore())
    assert run(gateway, request()).content == "ok"


def test_gateway_validates_its_routes() -> None:
    with pytest.raises(ValueError):
        Gateway({}, [])
    with pytest.raises(ValueError, match="no registrados"):
        Gateway({"a": StubProvider("a")}, [Route("b", "m")])
