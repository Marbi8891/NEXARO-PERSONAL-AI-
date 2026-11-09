from dataclasses import dataclass

from ai_gateway.providers.base import ChatProvider
from nexaro_core.config import Settings
from nexaro_core.database import Database
from nexaro_core.security import RateLimiter
from products.personal_ai.service import PersonalAIService


@dataclass(frozen=True)
class AppContext:
    """Dependencias ensambladas una vez por aplicación (sin estado global de módulo)."""

    settings: Settings
    database: Database
    limiter: RateLimiter
    key_limiter: RateLimiter  # peticiones por clave de API y minuto
    provider: ChatProvider
    personal_ai: PersonalAIService
