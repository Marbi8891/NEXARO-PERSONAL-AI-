"""Authenticated, read-only Obsidian endpoints for the local NEXARO Vault connector."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from nexaro_api.deps import CurrentUser
from nexaro_core.obsidian.vault import ObsidianVault, VaultNotConfiguredError, VaultPathError

router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])


def _vault() -> ObsidianVault:
    return ObsidianVault()


def _handle_config_error(exc: VaultNotConfiguredError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/status")
def status(user: CurrentUser) -> dict[str, Any]:
    return _vault().status()


@router.get("/notes")
def list_notes(
    user: CurrentUser,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    vault = _vault()
    try:
        notes = vault.list_notes(limit=limit, offset=offset)
        return {"notes": notes, "limit": limit, "offset": offset}
    except VaultNotConfiguredError as exc:
        raise _handle_config_error(exc) from exc


@router.get("/note/{note_path:path}")
def read_note(note_path: str, user: CurrentUser) -> dict[str, Any]:
    try:
        return _vault().read_note(note_path)
    except VaultNotConfiguredError as exc:
        raise _handle_config_error(exc) from exc
    except VaultPathError as exc:
        raise HTTPException(status_code=404, detail="Nota no encontrada") from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="La nota no es UTF-8 válido") from exc


@router.get("/search")
def search(
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return {"query": q, "results": _vault().search(q, limit=limit)}
    except VaultNotConfiguredError as exc:
        raise _handle_config_error(exc) from exc
