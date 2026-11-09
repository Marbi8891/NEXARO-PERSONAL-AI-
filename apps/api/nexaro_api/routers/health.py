import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from nexaro_api.deps import Ctx

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request, ctx: Ctx) -> dict[str, Any]:
    """Público. Con HEALTH_CACHE_SECONDS > 0 el resultado se reutiliza para que no sirva de sonda
    contra Ollama."""
    cached: tuple[float, bool] | None = getattr(request.app.state, "health_cache", None)
    now = time.monotonic()
    if cached is None or now - cached[0] >= ctx.settings.health_cache_seconds:
        cached = (now, await ctx.provider.health())
        request.app.state.health_cache = cached
    if not cached[1]:
        raise HTTPException(status_code=503, detail="Servicio de IA no disponible")
    return {"status": "ok", "ollama": "connected"}


@router.get("/health/live")
def live() -> dict[str, str]:
    """Liveness del proceso: no depende de Ollama (lo usa el HEALTHCHECK de Docker)."""
    return {"status": "ok"}
