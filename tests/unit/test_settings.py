from pathlib import Path

import pytest
from pydantic import ValidationError

from nexaro_core.config import Settings


def test_defaults_are_safe_for_local_development() -> None:
    settings = Settings()
    assert settings.environment == "development"
    assert settings.cookie_secure is False
    assert all(
        o.startswith("http://127.0.0.1") or o.startswith("http://localhost")
        for o in settings.allowed_origins
    )


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", "/data/x.db")
    monkeypatch.setenv("OLLAMA_MODEL", "otro:1b")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.test, http://b.test")
    settings = Settings()
    assert settings.database_path == Path("/data/x.db")
    assert settings.ollama_model == "otro:1b"
    assert settings.allowed_origins == frozenset({"http://a.test", "http://b.test"})


def test_production_requires_secure_cookie_and_https_origins() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(
            environment="production",
            cookie_secure=False,
            allowed_origins=frozenset({"https://a.test"}),
        )
    with pytest.raises(ValidationError, match="https"):
        Settings(
            environment="production",
            cookie_secure=True,
            allowed_origins=frozenset({"http://a.test"}),
        )
    ok = Settings(
        environment="production", cookie_secure=True, allowed_origins=frozenset({"https://a.test"})
    )
    assert ok.environment == "production"


def test_invalid_numeric_limits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(login_max_attempts=0)


CLOUD = {
    "ai_provider_order": ("ollama", "bedrock"),
    "ai_allow_cloud": True,
    "ai_cloud_monthly_budget_usd": 20.0,
    "aws_region": "eu-west-1",
    "bedrock_model_id": "m",
    "bedrock_price_input_per_1k": 0.003,
    "bedrock_price_output_per_1k": 0.015,
}


def test_gateway_defaults_to_local_only() -> None:
    settings = Settings()
    assert settings.ai_provider_order == ("ollama",) and settings.ai_allow_cloud is False


def test_provider_order_is_parsed_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_ORDER", "ollama, bedrock")
    monkeypatch.setenv("AI_ALLOW_CLOUD", "true")
    monkeypatch.setenv("AI_CLOUD_MONTHLY_BUDGET_USD", "20")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "m")
    monkeypatch.setenv("BEDROCK_PRICE_INPUT_PER_1K", "0.003")
    monkeypatch.setenv("BEDROCK_PRICE_OUTPUT_PER_1K", "0.015")
    assert Settings().ai_provider_order == ("ollama", "bedrock")


def test_cloud_cannot_be_enabled_by_accident() -> None:
    assert Settings(**CLOUD).ai_provider_order == ("ollama", "bedrock")
    for missing, message in (
        ("ai_allow_cloud", "AI_ALLOW_CLOUD"),
        ("ai_cloud_monthly_budget_usd", "AI_CLOUD_MONTHLY_BUDGET_USD"),
        ("aws_region", "AWS_REGION"),
        ("bedrock_price_output_per_1k", "BEDROCK_MODEL_ID"),
    ):
        with pytest.raises(ValidationError, match=message):
            Settings(**{**CLOUD, missing: False if missing == "ai_allow_cloud" else None})


def test_unknown_or_empty_provider_order_is_rejected() -> None:
    with pytest.raises(ValidationError, match="desconocidos"):
        Settings(ai_provider_order=("openai",))
    with pytest.raises(ValidationError):
        Settings(ai_provider_order=())
    with pytest.raises(ValidationError, match="SAGEMAKER_ENDPOINT"):
        Settings(**{**CLOUD, "ai_provider_order": ("sagemaker",)})
