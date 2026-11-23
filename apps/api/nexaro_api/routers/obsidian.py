"""Endpoints de solo lectura del Vault de Obsidian (conector local).

El Vault es un único directorio del host sin propietario por usuario ni por organización, así que
NO es un recurso compartido: solo lo leen los administradores de la plataforma y las cuentas de
OBSIDIAN_ALLOWED_EMAILS (SECURITY_REVIEW_V1.md, OBS-1). Cada usuario tiene su propio límite de
peticiones por minuto y las denegaciones quedan en la auditoría.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from nexaro_api.deps import Ctx, CurrentUser, client_ip
from nexaro_core.audit import record_event
from nexaro_core.obsidian.vault import (
    ObsidianVault,
    VaultNotConfiguredError,
    VaultNoteTooLargeError,
    VaultPathError,
)

router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])


def can_read_vault(ctx: Any, user: dict[str, Any]) -> bool:
    allowed = {email.lower() for email in ctx.settings.obsidian_allowed_emails}
    return user["role"] == "admin" or str(user["email"]).lower() in allowed


def _vault_reader(request: Request, ctx: Ctx, user: CurrentUser) -> ObsidianVault:
    if not can_read_vault(ctx, user):
        with ctx.database.connect() as db:
            record_event(
                db,
                "obsidian.access",
                "denied",
                actor_user_id=user["id"],
                ip=client_ip(request),
                details={"path": request.url.path},
            )
        raise HTTPException(status_code=403, detail="No tienes acceso al Vault de Obsidian")
    key = f"obsidian:{user['id']}"
    if ctx.obsidian_limiter.is_limited(key):
        raise HTTPException(
            status_code=429,
            detail="Demasiadas consultas al Vault. Espera un momento.",
            headers={"Retry-After": "30"},
        )
    ctx.obsidian_limiter.record(key)
    settings = ctx.settings
    # "" (no None): sin configuración en Settings no se recurre a la variable de entorno.
    return ObsidianVault(
        settings.obsidian_vault_path or "",
        max_note_bytes=settings.obsidian_max_note_bytes,
        max_files=settings.obsidian_max_files,
    )


Vault = Annotated[ObsidianVault, Depends(_vault_reader)]


def _handle_config_error(exc: VaultNotConfiguredError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/status")
def status(vault: Vault) -> dict[str, Any]:
    return vault.status()


@router.get("/notes")
def list_notes(
    vault: Vault,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    try:
        notes = vault.list_notes(limit=limit, offset=offset)
        return {"notes": notes, "limit": limit, "offset": offset}
    except VaultNotConfiguredError as exc:
        raise _handle_config_error(exc) from exc


@router.get("/note/{note_path:path}")
def read_note(note_path: str, vault: Vault) -> dict[str, Any]:
    try:
        return vault.read_note(note_path)
    except VaultNotConfiguredError as exc:
        raise _handle_config_error(exc) from exc
    except VaultPathError as exc:
        raise HTTPException(status_code=404, detail="Nota no encontrada") from exc
    except VaultNoteTooLargeError as exc:
        raise HTTPException(status_code=413, detail="La nota es demasiado grande") from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="La nota no es UTF-8 válido") from exc


@router.get("/search")
def search(
    vault: Vault,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return {"query": q, "results": vault.search(q, limit=limit)}
    except VaultNotConfiguredError as exc:
        raise _handle_config_error(exc) from exc
