from typing import Any

from fastapi import APIRouter, HTTPException

from nexaro_api.deps import Ctx

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(ctx: Ctx) -> dict[str, Any]:
    if not await ctx.provider.health():
        raise HTTPException(status_code=503, detail="Servicio de IA no disponible")
    return {"status": "ok", "ollama": "connected"}


@router.get("/health/live")
def live() -> dict[str, str]:
    """Liveness del proceso: no depende de Ollama (lo usa el HEALTHCHECK de Docker)."""
    return {"status": "ok"}
