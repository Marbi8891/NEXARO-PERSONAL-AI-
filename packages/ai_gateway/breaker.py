"""Cortacircuitos por proveedor: tras varios fallos de disponibilidad seguidos se deja de llamar
al proveedor durante un tiempo, para fallar en el acto en vez de esperar al tiempo de conexión."""

import time
from collections.abc import Callable
from typing import Literal

State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self, threshold: int, cooldown_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def failures(self) -> int:
        return self._failures

    @property
    def state(self) -> State:
        """Consulta sin efectos: pasado el enfriamiento, el siguiente intento es una sonda."""
        if self._opened_at is None:
            return "closed"
        return "half_open" if self._clock() - self._opened_at >= self._cooldown else "open"

    def allow(self) -> bool:
        """True si se puede llamar al proveedor. Pasado el enfriamiento deja pasar una sola sonda
        y vuelve a cerrar la puerta hasta saber su resultado."""
        state = self.state
        if state == "closed":
            return True
        if state == "half_open":
            self._opened_at = self._clock()
            return True
        return False

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._clock()
