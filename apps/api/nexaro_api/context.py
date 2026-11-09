from dataclasses import dataclass

from ai_gateway.providers.base import ChatProvider
from nexaro_core.config import Settings
from nexaro_core.database import Database
from nexaro_core.security import ConcurrencyGuard, RateLimiter
from products.personal_ai.service import PersonalAIService


@dataclass(frozen=True)
class AppContext:
    """Dependencias ensambladas una vez por aplicación (sin estado global de módulo)."""

    settings: Settings
    database: Database
    limiter: RateLimiter
    key_limiter: RateLimiter  # peticiones por clave de API y minuto
    ip_limiter: RateLimiter  # intentos de login por IP (umbral propio)
    chat_limiter: RateLimiter  # peticiones al modelo por usuario y minuto
    chat_guard: ConcurrencyGuard  # generaciones simultáneas
    provider: ChatProvider
    personal_ai: PersonalAIService
