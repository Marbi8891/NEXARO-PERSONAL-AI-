"""Qué se guarda cuando termina, falla o se cancela una respuesta en streaming."""

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from ai_gateway.schemas import CompletionRequest, StreamChunk
from nexaro_core.database import Database
from products.personal_ai.service import PersonalAIService
from tests.integration.test_chat_stream import StreamProvider


class NoDoneProvider(StreamProvider):
    """Emite fragmentos y cierra el flujo sin `done`."""

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        for piece in self.pieces:
            yield StreamChunk(content=piece)


class GatedProvider(StreamProvider):
    """No emite nada hasta que se abra la puerta (controla la cancelación sin dormir)."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        self.entered.set()
        await self.gate.wait()
        yield StreamChunk(content="nunca")


def stored(database: Database) -> list[tuple[str, str]]:
    with database.connect() as db:
        rows = db.execute("SELECT role, content FROM messages ORDER BY id").fetchall()
        return [(r["role"], r["content"]) for r in rows]


def conversations(database: Database) -> int:
    with database.connect() as db:
        return int(db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])


@pytest.fixture
def user_id(add_user: Callable[..., str]) -> str:
    return add_user("a@example.com")


def service(database: Database, provider: StreamProvider) -> PersonalAIService:
    return PersonalAIService(database, provider, "m")


def test_completed_stream_saves_the_full_answer(database: Database, user_id: str) -> None:
    async def scenario() -> list[dict]:
        _, events = await service(database, StreamProvider()).open_stream(user_id, "hola", None)
        return [e async for e in events]

    events = asyncio.run(scenario())

    assert events[-1]["event"] == "done"
    assert stored(database) == [("user", "hola"), ("assistant", "Hola, mundo")]


def test_provider_error_after_tokens_saves_no_partial_answer(
    database: Database, user_id: str
) -> None:
    provider = StreamProvider()
    provider.fail_after = 2

    async def scenario() -> list[dict]:
        _, events = await service(database, provider).open_stream(user_id, "hola", None)
        return [e async for e in events]

    events = asyncio.run(scenario())

    assert [e["event"] for e in events] == ["token", "token", "error"]
    assert stored(database) == []
    assert conversations(database) == 0


def test_client_cancel_after_tokens_keeps_the_partial_answer(
    database: Database, user_id: str
) -> None:
    async def scenario() -> None:
        _, events = await service(database, StreamProvider()).open_stream(user_id, "hola", None)
        assert (await events.__anext__())["event"] == "token"  # «Hola»
        await events.aclose()  # el cliente se va: GeneratorExit

    asyncio.run(scenario())

    assert stored(database) == [("user", "hola"), ("assistant", "Hola")]


def test_cancel_without_content_discards_the_turn_and_propagates(
    database: Database, user_id: str
) -> None:
    provider = GatedProvider()

    async def scenario() -> None:
        _, events = await service(database, provider).open_stream(user_id, "hola", None)
        task = asyncio.create_task(events.__anext__())
        await provider.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):  # no se traga la cancelación
            await task

    asyncio.run(scenario())

    assert stored(database) == []
    assert conversations(database) == 0


def test_stream_without_done_is_not_a_completed_answer(database: Database, user_id: str) -> None:
    async def scenario() -> list[dict]:
        _, events = await service(database, NoDoneProvider()).open_stream(user_id, "hola", None)
        return [e async for e in events]

    events = asyncio.run(scenario())

    assert events[-1] == {"event": "error", "message": "Error al consultar el servicio de IA"}
    assert all(e["event"] != "done" for e in events)
    assert stored(database) == []
