import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from ai_gateway.providers.base import ChatProvider
from nexaro_api.bootstrap import migrate
from nexaro_api.context import AppContext
from nexaro_api.gateway import build_gateway
from nexaro_api.routers import admin, auth, chat, health
from nexaro_core.config import Settings, get_settings
from nexaro_core.database import Database
from nexaro_core.security import RateLimiter
from products.personal_ai.service import PersonalAIService

logger = logging.getLogger("nexaro")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def create_app(
    settings: Settings | None = None, *, chat_provider: ChatProvider | None = None
) -> FastAPI:
    """Fábrica de la aplicación. Sin efectos al importar el módulo."""
    settings = settings or get_settings()
    database = Database(settings.database_path)
    if chat_provider is None:
        gateway = build_gateway(settings, database)
        provider: ChatProvider = gateway
        model = gateway.model
    else:  # inyectado (tests): sin política ni registro de uso
        provider, model = chat_provider, settings.ollama_model
    ctx = AppContext(
        settings=settings,
        database=database,
        limiter=RateLimiter(
            settings.login_max_attempts,
            settings.login_window_seconds,
            settings.login_max_tracked_keys,
        ),
        provider=provider,
        personal_ai=PersonalAIService(database, provider, model),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.ensure_parent()
        try:
            migrate(database)
        except Exception:
            # No se arranca con un esquema a medias ni se silencia el fallo.
            logger.exception("Fallo en la migración; se aborta el arranque")
            raise
        yield

    production = settings.environment == "production"
    app = FastAPI(
        title="NEXARO",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )
    app.state.ctx = ctx

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    for module in (auth, admin, chat, health):
        app.include_router(module.router)

    if settings.frontend_path.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_path, html=True), name="frontend")

    return app
