"""Casos de uso de NEXARO Personal AI: conversaciones y chat. No conoce HTTP."""

import asyncio
import logging
import re
import sqlite3
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ai_gateway.errors import PolicyError, ProviderError
from ai_gateway.providers.base import ChatProvider
from ai_gateway.schemas import ChatMessage, CompletionRequest
from ai_gateway.streaming import stream_completion
from nexaro_core.database import Database, begin_write
from nexaro_core.timeseries import fill_days, last_days
from products.personal_ai import documents as docs
from products.personal_ai.prompts import build_system_prompt

logger = logging.getLogger("nexaro.chat")

HISTORY_LIMIT = 12
DOCUMENT_FRAGMENTS = 4  # fragmentos que se pasan al modelo cuando el usuario activa documentos
SHORT_QUERY_CHARS = 80
_CODE_HINTS = re.compile(
    r"```|\b(c[oó]digo|funci[oó]n|programa|script|clase|bug|error|python|javascript|"
    r"typescript|java|sql|html|css|docker|regex|algoritmo|implementa|refactoriza)\b",
    re.IGNORECASE,
)


def classify_query(message: str) -> str:
    """«code» (respuestas largas), «short» (saludos y preguntas breves) o «default»."""
    if _CODE_HINTS.search(message):
        return "code"
    return "short" if len(message.strip()) <= SHORT_QUERY_CHARS else "default"


def _source(hit: docs.Hit) -> dict[str, Any]:
    return {
        "document_id": hit.document_id,
        "title": hit.title,
        "ordinal": hit.ordinal,
        "snippet": hit.snippet,
        "score": hit.score,
    }


class ConversationNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ChatOutcome:
    conversation_id: str
    answer: str
    sources: list[dict[str, Any]] | None = None  # None: no se consultaron documentos


@dataclass(frozen=True)
class _Turn:
    """Un turno abierto: el historial enviado al modelo y lo que hay que deshacer si falla."""

    history: list[ChatMessage]
    user_message_id: int
    created_conversation: bool


class PersonalAIService:
    def __init__(
        self,
        database: Database,
        provider: ChatProvider,
        model: str,
        *,
        output_tokens: dict[str, int] | None = None,
        history_max_chars: int | None = None,
    ) -> None:
        self._database = database
        self._provider = provider
        self._model = model
        self._output_tokens = output_tokens or {}
        self._history_max_chars = history_max_chars

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None,
        *,
        organization_id: str | None = None,
        api_key_id: str | None = None,
        document_organization_id: str | None = None,
    ) -> ChatOutcome:
        conversation_id = conversation_id or str(uuid.uuid4())
        hits = await asyncio.to_thread(self._retrieve, document_organization_id, message)
        turn = await asyncio.to_thread(
            self._begin_turn, user_id, message, conversation_id, organization_id
        )
        request = self._build_request(
            user_id, message, turn.history, organization_id, api_key_id, hits
        )
        try:
            result = await self._provider.complete(request)
        except BaseException:
            # Sin respuesta no queda un mensaje del usuario huérfano en la conversación.
            self._discard_turn(conversation_id, turn)
            raise

        await asyncio.to_thread(self._save_answer, conversation_id, result.content)
        sources = None if hits is None else [_source(h) for h in hits]
        return ChatOutcome(conversation_id, result.content, sources)

    async def open_stream(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None,
        *,
        organization_id: str | None = None,
        api_key_id: str | None = None,
        document_organization_id: str | None = None,
    ) -> tuple[str, AsyncIterator[dict[str, Any]]]:
        """Prepara el turno (lanza ConversationNotFoundError antes de emitir nada) y devuelve
        el id de la conversación y el flujo de eventos: [sources], token*, done o error."""
        conversation_id = conversation_id or str(uuid.uuid4())
        hits = await asyncio.to_thread(self._retrieve, document_organization_id, message)
        turn = await asyncio.to_thread(
            self._begin_turn, user_id, message, conversation_id, organization_id
        )
        request = self._build_request(
            user_id, message, turn.history, organization_id, api_key_id, hits
        )
        sources = None if hits is None else [_source(h) for h in hits]
        return conversation_id, self._events(conversation_id, request, turn, sources)

    def _build_request(
        self,
        user_id: str,
        message: str,
        history: list[ChatMessage],
        organization_id: str | None,
        api_key_id: str | None,
        hits: list[docs.Hit] | None = None,
    ) -> CompletionRequest:
        """`hits` None: documentos desactivados. Lista (aunque vacía): activados. Los fragmentos
        solo viajan al modelo en este mensaje; en la base se guarda el texto tal cual lo escribió
        el usuario."""
        system = build_system_prompt(provider=self._provider.name.capitalize(), model=self._model)
        content = message
        if hits is not None:
            if hits:
                system += docs.DOCUMENT_RULES
                content = f"{docs.build_context(hits)}\n\nPregunta: {message}"
            else:
                system += docs.NO_FRAGMENTS_RULES
        return CompletionRequest(
            model=self._model,
            messages=[
                ChatMessage(role="system", content=system),
                *history,
                ChatMessage(role="user", content=content),
            ],
            max_output_tokens=self._output_tokens.get(classify_query(message)),
            user_id=user_id,
            organization_id=organization_id,
            api_key_id=api_key_id,
        )

    def _retrieve(self, organization_id: str | None, message: str) -> list[docs.Hit] | None:
        """Lectura previa al turno: si falla no queda nada que deshacer. El permiso sobre la
        organización lo comprueba el router; aquí solo se busca."""
        if organization_id is None:
            return None
        with self._database.connect() as db:
            return docs.search(db, organization_id, message, DOCUMENT_FRAGMENTS)

    def _begin_turn(
        self, user_id: str, message: str, conversation_id: str, organization_id: str | None
    ) -> _Turn:
        with self._database.connect() as db:
            created = self._claim_conversation(db, user_id, conversation_id, organization_id)
            history = self._recent_history(db, conversation_id, self._history_max_chars)
            cursor = db.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', ?)",
                (conversation_id, message),
            )
            user_message_id = int(cursor.lastrowid or 0)
        return _Turn(history, user_message_id, created)

    def _save_answer(self, conversation_id: str, content: str) -> None:
        with self._database.connect() as db:
            db.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', ?)",
                (conversation_id, content),
            )

    def _discard_turn(self, conversation_id: str, turn: _Turn) -> None:
        """Deshace un turno que no produjo respuesta: quita su mensaje de usuario y, si la
        conversación se creó en este turno y quedó vacía, la conversación. Escritura breve y
        síncrona: vale también cuando la tarea se está cancelando."""
        with self._database.connect() as db:
            db.execute("DELETE FROM messages WHERE id = ?", (turn.user_message_id,))
            if turn.created_conversation:
                db.execute(
                    "DELETE FROM conversations WHERE id = ? AND NOT EXISTS"
                    " (SELECT 1 FROM messages WHERE conversation_id = ?)",
                    (conversation_id, conversation_id),
                )

    async def _events(
        self,
        conversation_id: str,
        request: CompletionRequest,
        turn: _Turn,
        sources: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        parts: list[str] = []
        completed = False  # el proveedor terminó con `chunk.done`
        cancelled = False  # el cliente cerró el flujo o la tarea se canceló
        try:
            if sources is not None:
                yield {"event": "sources", "sources": sources}
            async for chunk in stream_completion(self._provider, request):
                if chunk.content:
                    parts.append(chunk.content)
                    yield {"event": "token", "content": chunk.content}
                if chunk.done:
                    completed = (
                        True  # antes de emitir: si el cliente se va aquí, la respuesta está entera
                    )
                    metrics = chunk.metrics
                    yield {
                        "event": "done",
                        "truncated": bool(metrics and metrics.done_reason == "length"),
                        "metrics": metrics.model_dump() if metrics else None,
                    }
                    if metrics:
                        logger.info(
                            "chat model=%s ttft_ms=%s load_ms=%s tokens=%s tps=%s total_ms=%s",
                            self._model,
                            metrics.ttft_ms,
                            metrics.load_ms,
                            metrics.tokens,
                            metrics.tokens_per_second,
                            metrics.total_ms,
                        )
            if not completed:
                # El flujo se cortó sin `done`: no es una respuesta completa.
                yield {"event": "error", "message": "Error al consultar el servicio de IA"}
        except (asyncio.CancelledError, GeneratorExit):
            cancelled = True
            raise  # la cancelación se propaga siempre
        except PolicyError as exc:
            yield {"event": "error", "message": str(exc)}
        except ProviderError:
            # El detalle del proveedor (URLs internas, etc.) no se devuelve al cliente.
            yield {"event": "error", "message": "Error al consultar el servicio de IA"}
        finally:
            # Escritura SÍNCRONA a propósito: durante una cancelación, el ámbito cancelado de
            # anyio vuelve a interrumpir cada `await`, y `asyncio.to_thread` dejaría el hilo
            # escribiendo sin que nadie lo espere (escritura huérfana). Es una operación breve.
            if parts and (completed or cancelled):
                # Completa, o parcial por cancelación del cliente («Detener», desconexión).
                self._save_answer(conversation_id, "".join(parts))
            else:
                # Fallo del proveedor, flujo sin `done` o cancelación sin contenido.
                self._discard_turn(conversation_id, turn)

    @staticmethod
    def _claim_conversation(
        db: sqlite3.Connection,
        user_id: str,
        conversation_id: str,
        organization_id: str | None = None,
    ) -> bool:
        """Devuelve True si la crea. Una conversación pertenece a su usuario y a su origen: las
        creadas con una clave de API quedan marcadas con la organización de la clave y solo se
        continúan con claves de ella."""
        owned = db.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ? AND organization_id IS ?",
            (conversation_id, user_id, organization_id),
        ).fetchone()
        if owned is not None:
            return False

        exists = db.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if exists is not None:
            # Existe pero es de otro usuario: misma respuesta que si no existiera.
            raise ConversationNotFoundError

        db.execute(
            "INSERT INTO conversations (id, user_id, organization_id) VALUES (?, ?, ?)",
            (conversation_id, user_id, organization_id),
        )
        return True

    @staticmethod
    def _recent_history(
        db: sqlite3.Connection, conversation_id: str, max_chars: int | None = None
    ) -> list[ChatMessage]:
        rows = db.execute(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, HISTORY_LIMIT),
        ).fetchall()
        history = [ChatMessage(role=row["role"], content=row["content"]) for row in rows]
        if max_chars is not None:  # de los más recientes hacia atrás, hasta el presupuesto
            kept: list[ChatMessage] = []
            used = 0
            for item in history:
                used += len(item.content)
                if used > max_chars and kept:
                    break
                kept.append(item)
            history = kept
        return list(reversed(history))

    def list_conversations(
        self, user_id: str, limit: int | None = None, organization_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Con `organization_id`, solo las creadas mediante claves de esa organización."""
        with self._database.connect() as db:
            rows = db.execute(
                """
                SELECT
                    c.id,
                    c.created_at,
                    COUNT(m.id) AS message_count,
                    MAX(m.created_at) AS last_activity,
                    (SELECT content FROM messages
                      WHERE conversation_id = c.id AND role = 'user'
                      ORDER BY id ASC LIMIT 1) AS title,
                    (SELECT content FROM messages
                      WHERE conversation_id = c.id
                      ORDER BY id DESC LIMIT 1) AS preview
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.user_id = ? AND (? IS NULL OR c.organization_id = ?)
                GROUP BY c.id
                ORDER BY COALESCE(MAX(m.created_at), c.created_at) DESC,
                         COALESCE(MAX(m.id), 0) DESC
                LIMIT ?
                """,
                (
                    user_id,
                    organization_id,
                    organization_id,
                    -1 if limit is None else limit,
                ),  # LIMIT -1 = sin límite en SQLite
            ).fetchall()
        return [dict(row) for row in rows]

    def activity(self, user_id: str, days: int = 14, recent: int = 5) -> dict[str, Any]:
        """Resumen de actividad del usuario: totales, mensajes por día y últimas conversaciones."""
        window = last_days(days)
        with self._database.connect() as db:
            totals = db.execute(
                """
                SELECT (SELECT COUNT(*) FROM conversations WHERE user_id = ?) AS conversations,
                       COUNT(m.id) AS messages, MAX(m.created_at) AS last_activity
                FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE c.user_id = ?
                """,
                (user_id, user_id),
            ).fetchone()
            per_day = db.execute(
                """
                SELECT date(m.created_at) AS day, COUNT(*) AS messages
                FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE c.user_id = ? AND date(m.created_at) >= ?
                GROUP BY day
                """,
                (user_id, window[0]),
            ).fetchall()
        return {
            "conversations": int(totals["conversations"]),
            "messages": int(totals["messages"]),
            "last_activity": totals["last_activity"],
            "daily": fill_days(window, {r["day"]: int(r["messages"]) for r in per_day}, "messages"),
            "recent": self.list_conversations(user_id, limit=recent),
        }

    def get_conversation(
        self, user_id: str, conversation_id: str, organization_id: str | None = None
    ) -> dict[str, Any]:
        with self._database.connect() as db:
            conversation = db.execute(
                """
                SELECT id, created_at FROM conversations
                WHERE id = ? AND user_id = ? AND (? IS NULL OR organization_id = ?)
                """,
                (conversation_id, user_id, organization_id, organization_id),
            ).fetchone()
            if conversation is None:
                raise ConversationNotFoundError

            rows = db.execute(
                """
                SELECT id, role, content, created_at FROM messages
                WHERE conversation_id = ? ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()

        return {"conversation": dict(conversation), "messages": [dict(r) for r in rows]}

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        """Borra una conversación propia y todos sus mensajes. Misma respuesta (no encontrada)
        si no existe o es de otro usuario."""
        with self._database.connect() as db:
            begin_write(db)
            owned = db.execute(
                "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if owned is None:
                raise ConversationNotFoundError
            db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
