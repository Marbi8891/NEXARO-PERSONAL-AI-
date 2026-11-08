"""Casos de uso de NEXARO Personal AI: conversaciones y chat. No conoce HTTP."""

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from ai_gateway.providers.base import ChatProvider
from ai_gateway.schemas import ChatMessage, CompletionRequest
from nexaro_core.database import Database
from products.personal_ai.prompts import build_system_prompt

HISTORY_LIMIT = 12


class ConversationNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ChatOutcome:
    conversation_id: str
    answer: str


class PersonalAIService:
    def __init__(self, database: Database, provider: ChatProvider, model: str) -> None:
        self._database = database
        self._provider = provider
        self._model = model

    async def chat(self, user_id: str, message: str, conversation_id: str | None) -> ChatOutcome:
        conversation_id = conversation_id or str(uuid.uuid4())

        with self._database.connect() as db:
            self._claim_conversation(db, user_id, conversation_id)
            history = self._recent_history(db, conversation_id)
            db.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', ?)",
                (conversation_id, message),
            )

        messages = [
            ChatMessage(
                role="system",
                content=build_system_prompt(
                    provider=self._provider.name.capitalize(), model=self._model
                ),
            ),
            *history,
            ChatMessage(role="user", content=message),
        ]
        result = await self._provider.complete(
            CompletionRequest(model=self._model, messages=messages)
        )

        with self._database.connect() as db:
            db.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', ?)",
                (conversation_id, result.content),
            )

        return ChatOutcome(conversation_id=conversation_id, answer=result.content)

    @staticmethod
    def _claim_conversation(db: sqlite3.Connection, user_id: str, conversation_id: str) -> None:
        owned = db.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if owned is not None:
            return

        exists = db.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if exists is not None:
            # Existe pero es de otro usuario: misma respuesta que si no existiera.
            raise ConversationNotFoundError

        db.execute(
            "INSERT INTO conversations (id, user_id) VALUES (?, ?)", (conversation_id, user_id)
        )

    @staticmethod
    def _recent_history(db: sqlite3.Connection, conversation_id: str) -> list[ChatMessage]:
        rows = db.execute(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, HISTORY_LIMIT),
        ).fetchall()
        return [ChatMessage(role=row["role"], content=row["content"]) for row in reversed(rows)]

    def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
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
                WHERE c.user_id = ?
                GROUP BY c.id
                ORDER BY COALESCE(MAX(m.created_at), c.created_at) DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any]:
        with self._database.connect() as db:
            conversation = db.execute(
                "SELECT id, created_at FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
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
