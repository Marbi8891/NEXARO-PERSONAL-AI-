import logging
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ai_gateway.providers.base import ChatProvider
from nexaro_api.bootstrap import migrate
from nexaro_api.context import AppContext
from nexaro_api.gateway import build_gateway
from nexaro_api.limits import BodyLimitMiddleware
from nexaro_api.request_context import RequestContextMiddleware
from nexaro_api.routers import (
    admin,
    api_keys,
    auth,
    chat,
    dashboard,
    documents,
    expenses,
    health,
    organizations,
)
from nexaro_core.config import Settings, get_settings
from nexaro_core.database import Database
from nexaro_core.observability import configure_logging, request_id_var
from nexaro_core.security import ConcurrencyGuard, RateLimiter
from products.personal_ai.service import PersonalAIService

logger = logging.getLogger("nexaro")

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/woff2", ".woff2")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HSTS = "max-age=31536000; includeSubDomains"

# El frontend no usa scripts ni estilos en línea (lo verifica tests/security).
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; manifest-src 'self'; worker-src 'self'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
# Swagger UI necesita recursos externos y scripts en línea: solo fuera de producción.
CSP_EXEMPT_PATHS = ("/docs", "/redoc", "/openapi.json")


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
        ip_limiter=RateLimiter(
            settings.login_ip_max_attempts or settings.login_max_attempts,
            settings.login_window_seconds,
            settings.login_max_tracked_keys,
        ),
        chat_limiter=RateLimiter(
            settings.chat_requests_per_minute, 60, settings.login_max_tracked_keys
        ),
        chat_guard=ConcurrencyGuard(
            settings.chat_max_concurrent,
            settings.chat_max_concurrent_per_user,
            settings.ai_timeout_seconds + 30,
        ),
        key_limiter=RateLimiter(
            settings.api_key_requests_per_minute, 60, settings.login_max_tracked_keys
        ),
        provider=provider,
        personal_ai=PersonalAIService(
            database,
            provider,
            model,
            output_tokens={
                "short": settings.output_tokens_short,
                "default": settings.output_tokens_default,
                "code": settings.output_tokens_code,
            },
            history_max_chars=settings.chat_history_max_chars,
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_format)
        database.ensure_parent()
        try:
            migrate(database)
        except Exception:
            # No se arranca con un esquema a medias ni se silencia el fallo.
            logger.exception("Fallo en la migración; se aborta el arranque")
            raise
        yield
        close = getattr(provider, "aclose", None)
        if close is not None:  # cierra el cliente HTTP único hacia Ollama
            await close()

    production = settings.environment == "production"
    docs_enabled = (
        settings.api_docs
        if settings.api_docs is not None
        else settings.environment == "development"
    ) and not production
    app = FastAPI(
        title="NEXARO",
        version="0.3.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.ctx = ctx

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith(CSP_EXEMPT_PATHS):
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if settings.cookie_secure:  # HTTPS (producción): el navegador no vuelve a usar HTTP
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        if request.url.path.startswith("/api/"):  # respuestas autenticadas: nada de caché
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(RequestContextMiddleware)  # el último añadido es el más externo

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Corre fuera del middleware de contexto: el id viaja en el scope, no en el contextvar.
        request_id = request.scope.get("nexaro_request_id")
        token = request_id_var.set(request_id)
        try:
            logger.error(
                "unhandled_exception",
                exc_info=exc,
                extra={"fields": {"method": request.method, "path": request.url.path}},
            )
        finally:
            request_id_var.reset(token)
        return JSONResponse(
            {"detail": "Error interno", "request_id": request_id},
            status_code=500,
            headers={"X-Request-ID": request_id or ""},
        )

    for module in (
        auth,
        admin,
        api_keys,
        chat,
        dashboard,
        documents,
        expenses,
        health,
        organizations,
    ):
        app.include_router(module.router)

    if settings.frontend_path.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_path, html=True), name="frontend")

    return app
