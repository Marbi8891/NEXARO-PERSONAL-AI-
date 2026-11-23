"""Servidor de demostración para las capturas del producto (tests/frontend/screenshots.mjs).

Igual que server.py (BD temporal, Gateway real), pero con cuentas neutras y un proveedor sustituto:
la aplicación real responde, pero no hay un modelo real. Las capturas NO muestran texto generado; si
alguna lo mostrara, el texto se identifica a sí mismo como marcador de demostración.

Requiere PYTHONPATH con packages/ y apps/api (lo fija `make screenshots`).
"""

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

PORT = int(os.environ.get("NEXARO_DEMO_PORT", "8766"))
ORIGIN = f"http://127.0.0.1:{PORT}"
PASSWORD = "demo-password-not-secret"  # cuenta efímera de una BD temporal
PLACEHOLDER = "[Marcador de demostración: no es una respuesta de un modelo]"


class DemoProvider:
    """Sustituto de Ollama: lista los modelos que mostraría un Ollama local típico."""

    name = "ollama"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content=PLACEHOLDER, model=request.model, provider=self.name)

    async def health(self) -> bool:
        return True

    async def list_models(self) -> list[dict[str, Any]]:
        return [
            {"name": "qwen2.5:3b", "size_bytes": 1_929_912_432, "parameter_size": "3.1B",
             "quantization": "Q4_K_M"},
            {"name": "llama3.2:3b", "size_bytes": 2_019_393_189, "parameter_size": "3.2B",
             "quantization": "Q4_K_M"},
        ]  # fmt: skip

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(content=PLACEHOLDER)
        yield StreamChunk(done=True, metrics=InferenceMetrics(ttft_ms=420.0, tokens=12))


def main() -> None:
    repo = Path(os.environ["REPO"])
    settings = Settings(
        database_path=Path(tempfile.mkdtemp()) / "demo.db",
        frontend_path=repo / "frontend",
        allowed_origins=frozenset({ORIGIN}),
    )
    database = Database(settings.database_path)
    migrate(database)
    accounts = [
        ("admin@example.com", "admin", True),
        ("analyst@example.com", "user", True),
        ("new.user@example.com", "user", False),  # solicitud pendiente: genera un aviso real
    ]
    with database.connect() as db:
        for email, role, approved in accounts:
            user_id = create_user(db, email, PASSWORD, approved=approved)
            db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    gateway = Gateway({"ollama": DemoProvider()}, [Route("ollama", "qwen2.5:3b")], GatewayPolicy())
    app: Any = create_app(settings, chat_provider=gateway)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
