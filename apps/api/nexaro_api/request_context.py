"""request_id por petición y línea de acceso estructurada (sin cabeceras, consulta ni cuerpo)."""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from nexaro_core.observability import request_id_var

logger = logging.getLogger("nexaro.access")
VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
QUIET_PATHS = frozenset({"/api/health/live"})  # el HEALTHCHECK de Docker, cada 30 s


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        scope["nexaro_request_id"] = request_id  # lo lee el manejador de errores no controlados
        started = time.perf_counter()
        status = 500

        async def tracking_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        finally:
            path = scope["path"]
            level = logging.DEBUG if path in QUIET_PATHS else logging.INFO
            if status >= 500:
                level = logging.ERROR
            logger.log(
                level,
                "request",
                extra={
                    "fields": {
                        "method": scope["method"],
                        "path": path,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "ip": scope["client"][0] if scope.get("client") else None,
                    }
                },
            )
            request_id_var.reset(token)
