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
