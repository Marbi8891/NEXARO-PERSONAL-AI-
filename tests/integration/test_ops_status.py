"""Panel de operaciones: /api/admin/status (OPERATIONS.md)."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.observability import RequestMetrics
from tests.conftest import ORIGIN, PASSWORD, FakeProvider, login


def test_status_is_admin_only(client: TestClient, logged_in: Callable[..., TestClient]) -> None:
    assert client.get("/api/admin/status").status_code == 401
    assert logged_in("normal@example.com").get("/api/admin/status").status_code == 403


def test_status_reports_components_without_secrets(
    logged_in: Callable[..., TestClient], provider: FakeProvider
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    admin.get("/api/conversations")
    body = admin.get("/api/admin/status").json()
    assert body["backend"]["status"] == "ok"
    assert body["ollama"]["status"] == "ok"
    assert body["database"]["status"] == "ok" and body["database"]["schema_version"] >= 7
    assert {a["id"] for a in body["agents"]} >= {"general"}
    assert body["requests"]["requests_total"] >= 2
    assert body["backups"]["status"] == "not_configured"
    assert set(body["system"]) == {"cpu", "memory", "disk"}
    text = json.dumps(body).lower()
    for leaked in (PASSWORD, "nexaro_session", "password_hash", "token_hash"):
        assert leaked.lower() not in text

    provider.healthy = False
    assert admin.get("/api/admin/status").json()["ollama"]["status"] == "unreachable"


def _app_with_backup_status(tmp_path: Path, provider: FakeProvider, status: Any) -> TestClient:
    status_file = tmp_path / "backup-status.json"
    if status is not None:
        status_file.write_text(json.dumps(status), encoding="utf-8")
    settings = Settings(
        database_path=tmp_path / "nexaro.db",
        frontend_path=tmp_path / "sin-frontend",
        allowed_origins=frozenset({ORIGIN}),
        backup_status_path=status_file,
    )
    client = TestClient(create_app(settings, chat_provider=provider))
    client.__enter__()
    from nexaro_core.database import Database
    from nexaro_core.identity import create_user

    with Database(settings.database_path).connect() as db:
        uid = create_user(db, "ops@example.com", PASSWORD, approved=True)
        db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
    assert login(client, "ops@example.com").status_code == 200
    return client


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, "never"),
        ({"ok": True, "finished_at": datetime.now(timezone.utc).isoformat()}, "ok"),
        (
            {
                "ok": True,
                "finished_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            },
            "stale",
        ),
        ({"ok": False, "error": "disco lleno", "finished_at": "2026-11-23T03:30:00"}, "failed"),
    ],
)
def test_backup_status_is_classified(
    tmp_path: Path, provider: FakeProvider, status: Any, expected: str
) -> None:
    client = _app_with_backup_status(tmp_path, provider, status)
    try:
        assert client.get("/api/admin/status").json()["backups"]["status"] == expected
    finally:
        client.__exit__(None, None, None)


def test_metrics_count_errors_and_percentiles_without_query_strings() -> None:
    metrics = RequestMetrics()
    for i in range(10):
        metrics.record("GET", "/api/conversations", 200, float(i), "r")
    metrics.record("POST", "/api/chat", 502, 50.0, "req-1")
    metrics.record(
        "GET", "/api/health/live", 200, 999.0, None
    )  # healthcheck: no cuenta en latencia
    snap = metrics.snapshot()
    assert snap["requests_total"] == 12
    assert snap["requests_by_class"]["5xx"] == 1
    assert snap["latency_ms"]["max"] == 50.0
    assert snap["recent_errors"][0]["request_id"] == "req-1"
    assert set(snap["recent_errors"][0]) == {"ts", "method", "path", "status", "request_id"}


def test_unhandled_errors_appear_in_recent_errors(
    logged_in: Callable[..., TestClient], app: Any
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    app.state.ctx.metrics.record("GET", "/api/x", 500, 1.0, "abc12345")
    errors = admin.get("/api/admin/status").json()["requests"]["recent_errors"]
    assert errors[0]["request_id"] == "abc12345"
