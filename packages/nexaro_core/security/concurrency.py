"""Límite de generaciones simultáneas (global y por clave) con caducidad de seguridad.

El modelo local corre en CPU: unas pocas generaciones a la vez bastan para dejarlo inservible. Las
peticiones que no caben se rechazan en el acto (no se encolan sin límite). Cada concesión caduca por
sí sola (`ttl`), de modo que una petición cancelada antes de empezar a emitir no retiene un hueco.
"""

import threading
import time
from collections.abc import Callable


class TooBusy(Exception):
    def __init__(self, scope: str) -> None:
        super().__init__(scope)
        self.scope = scope  # «user» o «global»


class Lease:
    def __init__(self, guard: "ConcurrencyGuard", key: str, token: int) -> None:
        self._guard = guard
        self._key = key
        self._token = token

    def release(self) -> None:
        self._guard._release(self._key, self._token)  # idempotente


class ConcurrencyGuard:
    def __init__(
        self,
        max_global: int,
        max_per_key: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_global = max_global
        self._max_per_key = max_per_key
        self._ttl = ttl_seconds
        self._clock = clock
        self._leases: dict[int, tuple[str, float]] = {}
        self._next = 0
        self._lock = threading.Lock()

    def acquire(self, key: str) -> Lease:
        now = self._clock()
        with self._lock:
            self._leases = {t: (k, d) for t, (k, d) in self._leases.items() if d > now}
            if sum(1 for k, _ in self._leases.values() if k == key) >= self._max_per_key:
                raise TooBusy("user")
            if len(self._leases) >= self._max_global:
                raise TooBusy("global")
            self._next += 1
            self._leases[self._next] = (key, now + self._ttl)
            return Lease(self, key, self._next)

    def _release(self, key: str, token: int) -> None:
        with self._lock:
            self._leases.pop(token, None)

    def active(self) -> int:
        with self._lock:
            return len(self._leases)
