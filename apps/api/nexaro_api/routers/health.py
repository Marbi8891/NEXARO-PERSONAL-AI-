import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from nexaro_api.deps import Ctx

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request, ctx: Ctx) -> dict[str, Any]:
    """Público: el servicio de IA responde y el modelo configurado está instalado.

    503 si Ollama no responde o si falta el modelo (el chat fallaría). El detalle es genérico: no
    revela el nombre del modelo. Con HEALTH_CACHE_SECONDS > 0 el resultado se reutiliza para que
    no sirva de sonda contra Ollama.
    """
    cached: tuple[float, bool, bool | None] | None = getattr(
        request.app.state, "health_cache", None
    )
    now = time.monotonic()
    if cached is None or now - cached[0] >= ctx.settings.health_cache_seconds:
        probe = getattr(ctx.provider, "readiness", None)
        if probe is not None:
            reachable, model_ready = await probe()
        else:
            reachable, model_ready = await ctx.provider.health(), None
        cached = (now, reachable, model_ready)
        request.app.state.health_cache = cached
    _, reachable, model_ready = cached
    if not reachable:
        raise HTTPException(status_code=503, detail="Servicio de IA no disponible")
    if model_ready is False:
        raise HTTPException(status_code=503, detail="Modelo de IA no disponible")
    return {
        "status": "ok",
        "ollama": "connected",
        "model": "ready" if model_ready else "unknown",
    }


@router.get("/health/live")
def live() -> dict[str, str]:
    """Liveness del proceso: no depende de Ollama (lo usa el HEALTHCHECK de Docker)."""
    return {"status": "ok"}
