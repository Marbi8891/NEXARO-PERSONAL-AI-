"""Métricas de peticiones en memoria para el panel de operaciones (OPERATIONS.md).

Pensado para un despliegue personal de una sola réplica: sin Prometheus ni almacenamiento
externo. Se reinicia con el proceso. Nunca guarda cabeceras, consulta, cuerpos ni IPs: solo método,
ruta (recortada), estado, duración e identificador de petición.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

MAX_SAMPLES = 2000
MAX_ERRORS = 25
MAX_PATH_CHARS = 160


def _percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
    return round(sorted_values[index], 1)


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = time.time()
        self._total = 0
        self._by_class: dict[str, int] = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
        self._durations: deque[float] = deque(maxlen=MAX_SAMPLES)
        self._errors: deque[dict[str, Any]] = deque(maxlen=MAX_ERRORS)

    def record(
        self, method: str, path: str, status: int, duration_ms: float, request_id: str | None
    ) -> None:
        bucket = f"{min(max(status // 100, 2), 5)}xx"
        with self._lock:
            self._total += 1
            self._by_class[bucket] += 1
            if path.startswith("/api/") and path != "/api/health/live":
                self._durations.append(duration_ms)
            if status >= 500:
                self._errors.append(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "method": method,
                        "path": path[:MAX_PATH_CHARS],
                        "status": status,
                        "request_id": request_id,
                    }
                )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = sorted(self._durations)
            return {
                "uptime_seconds": round(time.time() - self._started),
                "requests_total": self._total,
                "requests_by_class": dict(self._by_class),
                "latency_ms": {
                    "samples": len(durations),
                    "p50": _percentile(durations, 0.5),
                    "p95": _percentile(durations, 0.95),
                    "max": round(durations[-1], 1) if durations else None,
                },
                "recent_errors": list(reversed(self._errors)),
            }
