"""Logs estructurados: correlación por request_id, sin secretos y sin falsificación de líneas."""

import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.observability import JsonFormatter, configure_logging, redact, request_id_var
from tests.conftest import HEADERS, PASSWORD, FakeProvider


def lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    formatter = JsonFormatter()
    return [json.loads(formatter.format(r)) for r in caplog.records if r.name.startswith("nexaro")]


@pytest.fixture(autouse=True)
def _propagate() -> Any:
    # configure_logging desactiva la propagación; caplog la necesita para ver los registros.
    yield
    logging.getLogger("nexaro").propagate = True


def test_redact_hides_sensitive_keys_recursively_and_truncates() -> None:
    cleaned = redact({"user": "a", "Password": "x", "n": {"api_key": "k", "ok": 1}, "t": "y" * 900})
    assert cleaned["Password"] == "[REDACTED]" and cleaned["n"]["api_key"] == "[REDACTED]"
    assert cleaned["user"] == "a" and cleaned["n"]["ok"] == 1
    assert len(cleaned["t"]) == 501


def test_formatter_emits_one_json_line_even_with_newlines_in_the_message() -> None:
    record = logging.LogRecord("nexaro.x", logging.INFO, "f", 1, "linea1\nFALSA ok", None, None)
    record.fields = {"token": "secreto", "path": "/a"}  # type: ignore[attr-defined]
    token = request_id_var.set("req-12345678")
    try:
        out = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)
    assert "\n" not in out
    parsed = json.loads(out)
    assert parsed["request_id"] == "req-12345678" and parsed["token"] == "[REDACTED]"
    assert parsed["message"] == "linea1\nFALSA ok" and parsed["level"] == "INFO"
    assert parsed["ts"].endswith("+00:00")


def test_every_response_has_a_request_id_and_a_valid_incoming_one_is_kept(
    client: TestClient,
) -> None:
    generated = client.get("/api/health/live").headers["x-request-id"]
    assert len(generated) == 32
    kept = client.get("/api/health/live", headers={"X-Request-ID": "abc-12345678"})
    assert kept.headers["x-request-id"] == "abc-12345678"
    forged = client.get("/api/health/live", headers={"X-Request-ID": "mal\tid con espacios"})
    assert forged.headers["x-request-id"] != "mal\tid con espacios"
    too_short = client.get("/api/health/live", headers={"X-Request-ID": "a"})
    assert too_short.headers["x-request-id"] != "a"


def test_access_and_security_events_share_the_request_id_and_hold_no_secrets(
    client: TestClient, add_user: Callable[..., str], caplog: pytest.LogCaptureFixture
) -> None:
    add_user("a@example.com")
    with caplog.at_level(logging.INFO, logger="nexaro"):
        bad = client.post(
            "/api/auth/login",
            json={"email": "a@example.com", "password": "MALA-CLAVE-123456"},
            headers={**HEADERS, "X-Request-ID": "login-0001-abcd"},
        )
    assert bad.status_code == 401
    entries = [e for e in lines(caplog) if e["request_id"] == "login-0001-abcd"]
    kinds = {e["logger"] for e in entries}
    assert {"nexaro.security", "nexaro.access"} <= kinds
    security = next(e for e in entries if e["logger"] == "nexaro.security")
    assert security["event"] == "auth.login" and security["outcome"] == "failure"
    access = next(e for e in entries if e["logger"] == "nexaro.access")
    assert access["status"] == 401 and access["path"] == "/api/auth/login"
    dump = json.dumps(entries)
    assert "MALA-CLAVE-123456" not in dump and "a@example.com" not in dump


def test_chat_content_and_query_strings_are_never_logged(
    client: TestClient, add_user: Callable[..., str], caplog: pytest.LogCaptureFixture
) -> None:
    add_user("a@example.com")
    client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}, headers=HEADERS
    )
    with caplog.at_level(logging.DEBUG, logger="nexaro"):
        client.post("/api/chat", json={"message": "CONTENIDO-PRIVADO-777"}, headers=HEADERS)
        client.get("/api/conversations?token=SECRETO-EN-URL")
    dump = json.dumps(lines(caplog))
    assert "CONTENIDO-PRIVADO-777" not in dump and "SECRETO-EN-URL" not in dump


def test_unhandled_error_is_logged_with_request_id_and_returns_no_internals(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings, chat_provider=FakeProvider())

    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("detalle interno /app/secreto")

    with (
        TestClient(app, raise_server_exceptions=False) as client,
        caplog.at_level(logging.INFO, logger="nexaro"),
    ):
        logging.getLogger(
            "nexaro"
        ).propagate = True  # el arranque lo desactiva; caplog cuelga de root
        response = client.get("/api/boom", headers={"X-Request-ID": "boom-12345678"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Error interno", "request_id": "boom-12345678"}
    assert "secreto" not in response.text
    errors = [e for e in lines(caplog) if e["message"] == "unhandled_exception"]
    assert (
        errors
        and errors[0]["request_id"] == "boom-12345678"
        and "RuntimeError" in errors[0]["exception"]
    )


def test_configure_logging_is_idempotent_and_supports_text_format() -> None:
    configure_logging("WARNING", "json")
    configure_logging("INFO", "text")
    logger = logging.getLogger("nexaro")
    assert len(logger.handlers) == 1 and logger.level == logging.INFO
