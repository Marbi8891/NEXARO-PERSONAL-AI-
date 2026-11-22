import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_gateway.errors import ProviderError
from ai_gateway.gateway import Gateway, Route
from ai_gateway.providers.ollama import OllamaProvider
from ai_gateway.schemas import CompletionRequest, CompletionResult, InferenceMetrics, StreamChunk
from ai_gateway.usage import UsageStore
from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.database import Database
from products.personal_ai.service import PersonalAIService, classify_query

HEADERS = {"Origin": "http://127.0.0.1:8001"}


class StreamProvider:
    """Proveedor de pruebas con streaming real: emite los fragmentos de `pieces`."""

    name = "fake"

    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []
        self.pieces = ["Hola", ", ", "mundo"]
        self.fail_after: int | None = None
        self.closed = False

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise AssertionError("el streaming no debe usar complete()")

    async def health(self) -> bool:
        return True

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        self.requests.append(request)
        try:
            for index, piece in enumerate(self.pieces):
                if self.fail_after is not None and index == self.fail_after:
                    raise ProviderError("http://ollama:11434 caído")
                yield StreamChunk(content=piece)
            yield StreamChunk(
                done=True,
                metrics=InferenceMetrics(ttft_ms=12.0, tokens=3, done_reason="length"),
            )
        finally:
            self.closed = True


@pytest.fixture
def provider() -> StreamProvider:  # type: ignore[override]
    return StreamProvider()


def events_of(response: Any) -> list[dict[str, Any]]:
    lines = [ln for ln in response.text.split("\n\n") if ln.startswith("data: ")]
    return [json.loads(ln[len("data: ") :]) for ln in lines]


def stored(database: Database, conversation_id: str) -> list[tuple[str, str]]:
    with database.connect() as db:
        rows = db.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [(r["role"], r["content"]) for r in rows]


def test_stream_emits_start_tokens_done_and_persists_full_answer(
    logged_in: Callable[..., TestClient], database: Database, provider: StreamProvider
) -> None:
    client = logged_in("a@example.com")
    response = client.post("/api/chat/stream", json={"message": "hola"}, headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    events = events_of(response)
    assert [e["event"] for e in events] == ["start", "token", "token", "token", "done"]
    assert "".join(e["content"] for e in events if e["event"] == "token") == "Hola, mundo"
    assert events[-1]["truncated"] is True  # done_reason == "length"
    assert stored(database, events[0]["conversation_id"]) == [
        ("user", "hola"),
        ("assistant", "Hola, mundo"),
    ]


def test_stream_requires_session_and_valid_origin(
    client: TestClient, logged_in: Callable[..., TestClient]
) -> None:
    assert (
        client.post("/api/chat/stream", json={"message": "x"}, headers=HEADERS).status_code == 401
    )
    user = logged_in("a@example.com")
    assert user.post("/api/chat/stream", json={"message": "x"}).status_code == 403


def test_stream_cannot_continue_someone_elses_conversation(
    logged_in: Callable[..., TestClient],
) -> None:
    owner = logged_in("a@example.com")
    other = logged_in("b@example.com")
    first = events_of(owner.post("/api/chat/stream", json={"message": "hola"}, headers=HEADERS))
    response = other.post(
        "/api/chat/stream",
        json={"message": "x", "conversation_id": first[0]["conversation_id"]},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_stream_provider_error_mid_stream_is_generic_and_discards_the_turn(
    logged_in: Callable[..., TestClient], database: Database, provider: StreamProvider
) -> None:
    provider.fail_after = 1
    client = logged_in("a@example.com")
    response = client.post("/api/chat/stream", json={"message": "hola"}, headers=HEADERS)

    events = events_of(response)
    assert events[-1] == {"event": "error", "message": "Error al consultar el servicio de IA"}
    assert "ollama" not in response.text and "11434" not in response.text
    # Un parcial de un proveedor fallido no queda como respuesta normal del asistente.
    assert stored(database, events[0]["conversation_id"]) == []


def test_stream_continues_conversation_with_history(
    logged_in: Callable[..., TestClient], provider: StreamProvider
) -> None:
    client = logged_in("a@example.com")
    first = events_of(client.post("/api/chat/stream", json={"message": "uno"}, headers=HEADERS))
    conversation_id = first[0]["conversation_id"]
    client.post(
        "/api/chat/stream",
        json={"message": "dos", "conversation_id": conversation_id},
        headers=HEADERS,
    )
    roles = [(m.role, m.content) for m in provider.requests[-1].messages]
    assert roles[1:] == [("user", "uno"), ("assistant", "Hola, mundo"), ("user", "dos")]


def test_non_streaming_provider_is_served_as_single_chunk(
    settings: Settings, database: Database, add_user: Callable[..., str]
) -> None:
    from tests.conftest import FakeProvider, login

    app = create_app(settings, chat_provider=FakeProvider())
    with TestClient(app) as client:
        add_user("a@example.com")
        assert login(client, "a@example.com").status_code == 200
        events = events_of(
            client.post("/api/chat/stream", json={"message": "hola"}, headers=HEADERS)
        )
    assert [e["event"] for e in events] == ["start", "token", "done"]
    assert events[1]["content"] == "respuesta de prueba"


def test_cancelling_the_stream_keeps_what_was_generated_and_closes_the_provider(
    database: Database, provider: StreamProvider, add_user: Callable[..., str]
) -> None:
    user_id = add_user("a@example.com")
    service = PersonalAIService(database, provider, "m")

    async def scenario() -> str:
        conversation_id, events = await service.open_stream(user_id, "hola", None)
        first = await anext(events)  # type: ignore[arg-type]
        assert first == {"event": "token", "content": "Hola"}
        await events.aclose()  # type: ignore[attr-defined]  # el cliente pulsa «Detener»
        return conversation_id

    conversation_id = asyncio.run(scenario())
    assert provider.closed is True
    assert stored(database, conversation_id) == [("user", "hola"), ("assistant", "Hola")]


def test_history_is_trimmed_to_the_character_budget(
    database: Database, provider: StreamProvider, add_user: Callable[..., str]
) -> None:
    user_id = add_user("a@example.com")
    service = PersonalAIService(database, provider, "m", history_max_chars=50)

    async def scenario() -> None:
        conversation_id, events = await service.open_stream(user_id, "a" * 40, None)
        _ = [e async for e in events]
        _, events = await service.open_stream(user_id, "b" * 40, conversation_id)
        _ = [e async for e in events]
        _, events = await service.open_stream(user_id, "pregunta", conversation_id)
        _ = [e async for e in events]

    asyncio.run(scenario())
    sent = provider.requests[-1].messages[1:-1]
    assert sum(len(m.content) for m in sent) <= 50 or len(sent) == 1
    assert sent[-1].role == "assistant"  # se conserva lo más reciente


def test_output_budget_follows_the_kind_of_query(
    database: Database, provider: StreamProvider, add_user: Callable[..., str]
) -> None:
    user_id = add_user("a@example.com")
    service = PersonalAIService(
        database, provider, "m", output_tokens={"short": 11, "default": 22, "code": 33}
    )

    async def ask(text: str) -> int | None:
        _, events = await service.open_stream(user_id, text, None)
        _ = [e async for e in events]
        return provider.requests[-1].max_output_tokens

    assert asyncio.run(ask("hola")) == 11
    assert asyncio.run(ask("escribe una función en python que ordene")) == 33
    assert asyncio.run(ask("explícame con detalle " + "cómo funciona la fotosíntesis " * 3)) == 22


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("hola", "short"),
        ("```py\nprint(1)\n```", "code"),
        ("tengo un error en mi script", "code"),
        ("x " * 60, "default"),
    ],
)
def test_classify_query(message: str, kind: str) -> None:
    assert classify_query(message) == kind


def test_real_gateway_streams_from_ollama_and_records_inference_metrics(
    settings: Settings, database: Database, add_user: Callable[..., str]
) -> None:
    from tests.conftest import login

    lines = [
        {"message": {"content": "ho"}, "done": False},
        {"message": {"content": "la"}, "done": False},
        {
            "message": {"content": ""},
            "done": True,
            "done_reason": "stop",
            "load_duration": 2_500_000_000,
            "prompt_eval_duration": 400_000_000,
            "eval_duration": 1_000_000_000,
            "total_duration": 4_000_000_000,
            "prompt_eval_count": 30,
            "eval_count": 10,
        },
    ]
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())

    gateway = Gateway(
        {
            "ollama": OllamaProvider(
                "http://ollama:11434",
                transport=httpx.MockTransport(handler),
                keep_alive="30m",
                num_ctx=4096,
            )
        },
        [Route("ollama", "qwen-test")],
        usage=UsageStore(database),
    )
    with TestClient(create_app(settings, chat_provider=gateway)) as client:
        add_user("a@example.com")
        assert login(client, "a@example.com").status_code == 200
        events = events_of(
            client.post("/api/chat/stream", json={"message": "hola"}, headers=HEADERS)
        )

    assert [e["event"] for e in events] == ["start", "token", "token", "done"]
    metrics = events[-1]["metrics"]
    assert metrics["load_ms"] == 2500.0 and metrics["tokens"] == 10
    assert metrics["ttft_ms"] is not None
    sent = seen[0]
    assert sent["stream"] is True and sent["keep_alive"] == "30m"
    assert sent["options"]["num_ctx"] == 4096

    (row,) = UsageStore(database).inference(days=1)
    assert row["cold_loads"] == 1 and row["requests"] == 1
    assert row["avg_load_ms"] == 2500.0


def test_admin_usage_exposes_inference_section(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    body = admin.get("/api/admin/usage").json()
    assert body["inference"] == []
