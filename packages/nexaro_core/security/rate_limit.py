"""Limitador de intentos en memoria con ventana deslizante y memoria acotada.

Limitaciones asumidas (ADR-0003): estado por proceso, se reinicia al reiniciar y no se comparte
entre réplicas. Con varias réplicas hay que moverlo a un almacén compartido (p. ej. ElastiCache).
"""

import threading
import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        max_keys: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        return [t for t in self._attempts.get(key, []) if now - t < self._window]

    def is_limited(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            attempts = self._recent(key, now)
            if attempts:
                self._attempts[key] = attempts
            else:
                self._attempts.pop(key, None)
            return len(attempts) >= self._max_attempts

    def record(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            if key not in self._attempts and len(self._attempts) >= self._max_keys:
                self._evict(now)
            attempts = self._recent(key, now)
            attempts.append(now)
            self._attempts[key] = attempts

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._attempts)

    def _evict(self, now: float) -> None:
        for stale in [k for k in self._attempts if not self._recent(k, now)]:
            del self._attempts[stale]
        if len(self._attempts) >= self._max_keys:
            oldest = min(self._attempts, key=lambda k: self._attempts[k][-1])
            del self._attempts[oldest]
