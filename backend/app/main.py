
import os
import sqlite3
import uuid

from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


OLLAMA_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", "/data/nexaro.db")
)

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

FRONTEND_PATH = Path("/app/frontend")


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    with get_connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
            )
        """)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="NEXARO Personal AI",
    version="0.1.0",
    lifespan=lifespan
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                f"{OLLAMA_URL}/api/tags"
            )
            response.raise_for_status()

        models = [
            model["name"]
            for model in response.json().get("models", [])
        ]

        return {
            "status": "ok",
            "ollama": "connected",
            "configured_model": MODEL,
            "available_models": models
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama no disponible: {str(exc)}"
        )


@app.post("/api/chat")
async def chat(request: ChatRequest):
    conversation_id = (
        request.conversation_id or str(uuid.uuid4())
    )

    with get_connection() as db:
        db.execute(
            """
            INSERT OR IGNORE INTO conversations (id)
            VALUES (?)
            """,
            (conversation_id,)
        )

        history = db.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT 12
            """,
            (conversation_id,)
        ).fetchall()

        history = list(reversed(history))

        db.execute(
            """
            INSERT INTO messages
                (conversation_id, role, content)
            VALUES (?, 'user', ?)
            """,
            (conversation_id, request.message)
        )

    messages = [
        {
            "role": "system",
            "content": (
                "Eres NEXARO Personal AI, un asistente "
                "personal que responde en español. "
                "Sé claro, preciso y reconoce cuando "
                "no conoces una respuesta. No afirmes "
                "haber ejecutado acciones que no has realizado."
            )
        }
    ]

    messages.extend([
        {
            "role": row["role"],
            "content": row["content"]
        }
        for row in history
    ])

    messages.append({
        "role": "user",
        "content": request.message
    })

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": False
                }
            )

            response.raise_for_status()

        answer = response.json()["message"]["content"]

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error al consultar Ollama: {str(exc)}"
        )

    with get_connection() as db:
        db.execute(

            """
            INSERT INTO messages
                (conversation_id, role, content)
            VALUES (?, 'assistant', ?)
            """,
            (conversation_id, answer)
        )

    return {
        "conversation_id": conversation_id,
        "answer": answer
    }



@app.get("/api/conversations")
async def list_conversations():
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT
                c.id,
                c.created_at,
                COUNT(m.id) AS message_count,
                MAX(m.created_at) AS last_activity,
                (
                    SELECT content
                    FROM messages
                    WHERE conversation_id = c.id
                      AND role = 'user'
                    ORDER BY id ASC
                    LIMIT 1
                ) AS title,
                (
                    SELECT content
                    FROM messages
                    WHERE conversation_id = c.id
                    ORDER BY id DESC
                    LIMIT 1
                ) AS preview
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY COALESCE(MAX(m.created_at), c.created_at) DESC
            """
        ).fetchall()

    return {"conversations": [dict(row) for row in rows]}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    with get_connection() as db:
        conversation = db.execute(
            "SELECT id, created_at FROM conversations WHERE id = ?",
            (conversation_id,)
        ).fetchone()

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada"
            )

        rows = db.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,)
        ).fetchall()

    return {
        "conversation": dict(conversation),
        "messages": [dict(row) for row in rows]
    }


if FRONTEND_PATH.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_PATH, html=True), name="frontend")
