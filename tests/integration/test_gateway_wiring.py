from collections.abc import Callable

from fastapi.testclient import TestClient

from ai_gateway.gateway import Gateway
from ai_gateway.usage import UsageStore
from nexaro_api.gateway import build_gateway
from nexaro_core.config import Settings
from nexaro_core.database import Database

HEADERS = {"Origin": "http://127.0.0.1:8001"}


def test_default_settings_build_a_local_only_gateway(
    settings: Settings, database: Database
) -> None:
    gateway = build_gateway(settings, database)
    assert isinstance(gateway, Gateway)
    assert (gateway.name, gateway.model) == ("ollama", settings.ollama_model)


def test_cloud_settings_build_bedrock_route_with_prices(
    settings: Settings, database: Database
) -> None:
    cloud = settings.model_copy(
        update={
            "ai_provider_order": ("ollama", "bedrock"),
            "ai_allow_cloud": True,
            "ai_cloud_monthly_budget_usd": 10.0,
            "aws_region": "eu-west-1",
            "bedrock_model_id": "m",
            "bedrock_price_input_per_1k": 0.003,
            "bedrock_price_output_per_1k": 0.015,
        }
    )
    gateway = build_gateway(cloud, database)
    assert gateway.name == "ollama"  # la nube solo como respaldo, nunca primera por accidente


def test_admin_usage_summary(logged_in: Callable[..., TestClient], database: Database) -> None:
    admin = logged_in("admin@example.com", role="admin")
    user = logged_in("user@example.com")
    UsageStore(database).record(
        user_id=None, provider="ollama", model="m", status="ok", input_tokens=3, output_tokens=2,
        cost_usd=0.0,
    )  # fmt: skip

    assert user.get("/api/admin/usage").status_code == 403
    body = admin.get("/api/admin/usage").json()
    assert body["usage"][0]["requests"] == 1 and body["usage"][0]["input_tokens"] == 3
    assert body["month_cost_usd"] == 0.0


def test_chat_through_the_real_gateway_records_usage(
    settings: Settings, database: Database, add_user: Callable[..., str]
) -> None:
    """Gateway real (no el sustituto de pruebas) con un proveedor local simulado por transporte."""
    import httpx

    from ai_gateway.gateway import Route
    from ai_gateway.providers.ollama import OllamaProvider
    from nexaro_api.main import create_app

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"content": "hola"}, "prompt_eval_count": 4, "eval_count": 2}
        )

    gateway = Gateway(
        {"ollama": OllamaProvider("http://ollama:11434", transport=httpx.MockTransport(handler))},
        [Route("ollama", "qwen-test")],
        usage=UsageStore(database),
    )
    with TestClient(create_app(settings, chat_provider=gateway)) as client:
        add_user("a@example.com")
        assert client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"},
            headers=HEADERS,
        ).status_code == 200  # fmt: skip
        reply = client.post("/api/chat", json={"message": "hola"}, headers=HEADERS)
        assert reply.status_code == 200 and reply.json()["answer"] == "hola"

    [row] = UsageStore(database).summary()
    assert (row["provider"], row["model"], row["status"], row["output_tokens"]) == (
        "ollama", "qwen-test", "ok", 2,
    )  # fmt: skip
