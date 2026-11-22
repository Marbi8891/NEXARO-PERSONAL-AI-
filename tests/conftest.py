from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_gateway.schemas import CompletionRequest, CompletionResult
from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.database import Database
from nexaro_core.identity import create_user

ORIGIN = "http://127.0.0.1:8001"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "correct-horse-battery"


class FakeProvider:
    """Proveedor de IA de pruebas: nunca sale a la red."""

    name = "fake"

    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []
        self.error: Exception | None = None
        self.healthy = True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return CompletionResult(
            content="respuesta de prueba", model=request.model, provider=self.name
        )

    async def health(self) -> bool:
        return self.healthy


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "nexaro.db",
        frontend_path=tmp_path / "sin-frontend",
        allowed_origins=frozenset({ORIGIN}),
    )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def app(settings: Settings, provider: FakeProvider) -> Any:
    return create_app(settings, chat_provider=provider)


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as test_client:  # ejecuta lifespan: migración incluida
        yield test_client


@pytest.fixture
def database(settings: Settings) -> Database:
    return Database(settings.database_path)


@pytest.fixture
def add_user(client: TestClient, database: Database) -> Callable[..., str]:
    def _add(email: str, *, role: str = "user", approved: bool = True, active: bool = True) -> str:
        with database.connect() as db:
            user_id = create_user(db, email, PASSWORD, approved=approved)
            db.execute(
                "UPDATE users SET role = ?, is_active = ? WHERE id = ?",
                (role, 1 if active else 0, user_id),
            )
        return user_id

    return _add


def login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers=HEADERS
    )


@pytest.fixture
def logged_in(
    app: Any, client: TestClient, add_user: Callable[..., str]
) -> Callable[..., TestClient]:
    """Crea un cliente HTTP independiente (su propio jar de cookies) con sesión iniciada."""

    def _make(email: str, **kwargs: Any) -> TestClient:
        add_user(email, **kwargs)
        other = TestClient(app)
        assert login(other, email).status_code == 200
        return other

    return _make


def audit_actions(database: Database) -> list[str]:
    with database.connect() as db:
        return [r["action"] for r in db.execute("SELECT action FROM audit_events ORDER BY id")]
