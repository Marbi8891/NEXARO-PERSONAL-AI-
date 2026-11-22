"""Servidor efímero (BD temporal, proveedor de IA falso) para tests/frontend/e2e.mjs.

Requiere PYTHONPATH con packages/ y apps/api (lo fija run.sh).
"""

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import uvicorn

from ai_gateway.gateway import Gateway, Route
from ai_gateway.policy import GatewayPolicy
from ai_gateway.schemas import CompletionRequest, CompletionResult, InferenceMetrics, StreamChunk
from nexaro_api.bootstrap import migrate
from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.database import Database
from nexaro_core.identity import create_user

ORIGIN = "http://127.0.0.1:8765"
PASSWORD = "correct-horse-battery"


class FakeProvider:
    name = "fake"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        # Devuelve HTML a propósito: el frontend debe mostrarlo como texto.
        return CompletionResult(
            content="Hola <b>mundo</b> desde el modelo falso", model=request.model, provider="fake"
        )

    async def health(self) -> bool:
        return True

    async def list_models(self) -> list[dict[str, Any]]:
        """Modelos «instalados» del proveedor falso (para el selector de modelo)."""
        return [
            {"name": name, "size_bytes": 1, "parameter_size": size, "quantization": None}
            for name, size in (("qwen2.5:3b", "3B"), ("llama3.2:latest", "3B"))
        ]

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Streaming de pruebas: «lento» genera durante varios segundos (para probar «Detener»)
        y «codigo» devuelve Markdown con un bloque de código y HTML que debe verse como texto."""
        asked = request.messages[-1].content
        if "lento" in asked:
            for _ in range(200):
                yield StreamChunk(content="parte ")
                await asyncio.sleep(0.05)
        elif "quemodelo" in asked:
            yield StreamChunk(content=f"respondo con {request.model}")
        elif "codigo" in asked:
            for piece in ["**Hola** con `x`\n\n", "```py\nprint(1)\n", "```\n", "<b>x</b>"]:
                yield StreamChunk(content=piece)
        else:
            for piece in ["Hola <b>mundo</b> ", "desde el modelo ", "falso"]:
                yield StreamChunk(content=piece)
        yield StreamChunk(done=True, metrics=InferenceMetrics(ttft_ms=1.0, tokens=3))


def main() -> None:
    repo = Path(os.environ["REPO"])
    settings = Settings(
        database_path=Path(tempfile.mkdtemp()) / "e2e.db",
        frontend_path=repo / "frontend",
        allowed_origins=frozenset({ORIGIN}),
    )
    database = Database(settings.database_path)
    migrate(database)
    accounts: list[tuple[str, str, bool]] = [
        ("admin@x.io", "admin", True),
        ("user@x.io", "user", True),
        ("pend@x.io", "user", False),
    ]
    with database.connect() as db:
        for email, role, approved in accounts:
            user_id = create_user(db, email, PASSWORD, approved=approved)
            db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    # Detrás de un Gateway real: el selector de modelo y su comprobación son los de producción.
    gateway = Gateway({"fake": FakeProvider()}, [Route("fake", "qwen2.5:3b")], GatewayPolicy())
    app: Any = create_app(settings, chat_provider=gateway)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
