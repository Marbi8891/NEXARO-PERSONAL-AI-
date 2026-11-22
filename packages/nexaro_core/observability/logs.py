"""Logs estructurados (una línea JSON por evento) con correlación por `request_id`.

Salen por stdout: la rotación y la retención las gestiona Docker (`logging:` en compose.yaml). Un
registro nunca lleva contraseñas, tokens ni cuerpos de petición: los campos con nombre sensible se
sustituyen y JSON escapa los saltos de línea (no se puede falsificar una línea de log).
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

SENSITIVE = ("password", "passwd", "token", "secret", "authorization", "cookie", "api_key", "hash")
MAX_VALUE_CHARS = 500


def current_request_id() -> str | None:
    return request_id_var.get()


def redact(value: Any) -> Any:
    """Copia con los valores de claves sensibles ocultos y los textos largos recortados."""
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if any(s in str(k).lower() for s in SENSITIVE) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + "…"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(redact(fields))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = str(record.getMessage()).replace("\n", "\\n").replace("\r", "\\r")
        record.args = None
        rid = getattr(record, "request_id", None) or request_id_var.get()
        base = super().format(record)
        return f"{base} request_id={rid}" if rid else base


_factory_installed = False


def _install_record_factory() -> None:
    """Cada registro se marca con el request_id en el momento de emitirse (no al formatearse)."""
    global _factory_installed
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        record.request_id = request_id_var.get()
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Idempotente: sustituye el manejador de los loggers `nexaro*` y silencia el acceso de uvicorn
    (lo reemplaza la línea de acceso propia, que lleva `request_id`)."""
    _install_record_factory()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else _TextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger("nexaro")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True
