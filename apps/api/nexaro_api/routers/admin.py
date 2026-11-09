import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ai_gateway.usage import UsageStore
from nexaro_api.deps import AdminUser, Ctx, client_ip, validate_origin
from nexaro_api.schemas import (
    AdminCreateUserRequest,
    RegistrationSettingRequest,
    UserActiveRequest,
)
from nexaro_core.audit import list_events, record_event, security_summary
from nexaro_core.database import begin_write
from nexaro_core.identity import (
    LastAdminError,
    approve_user,
    create_user,
    ensure_not_last_admin,
    get_registration_enabled,
    list_users,
    reject_user,
    revoke_user_sessions,
    set_registration_enabled,
    set_user_active,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def admin_list_users(admin: AdminUser, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {
            "users": list_users(db),
            "public_registration_enabled": get_registration_enabled(db),
        }


@router.post("/users", status_code=201)
def admin_create_user(
    request: Request, credentials: AdminCreateUserRequest, admin: AdminUser, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)

    with ctx.database.connect() as db:
        try:
            user_id = create_user(db, credentials.email, credentials.password, approved=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="Ya existe una cuenta con ese correo"
            ) from exc
        record_event(
            db,
            "admin.user_create",
            "success",
            actor_user_id=admin["id"],
            target_type="user",
            target_id=user_id,
            ip=client_ip(request),
        )

    return {
        "created": True,
        "user_id": user_id,
        "role": "user",
        "approval_status": "approved",
        "is_active": True,
    }


@router.post("/users/{user_id}/approve")
def admin_approve_user(
    user_id: str, request: Request, admin: AdminUser, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)

    with ctx.database.connect() as db:
        if not approve_user(db, user_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        record_event(
            db,
            "admin.user_approve",
            "success",
            actor_user_id=admin["id"],
            target_type="user",
            target_id=user_id,
            ip=client_ip(request),
        )

    return {"updated": True, "approval_status": "approved", "is_active": True}


@router.post("/users/{user_id}/reject")
def admin_reject_user(user_id: str, request: Request, admin: AdminUser, ctx: Ctx) -> dict[str, Any]:
    validate_origin(request, ctx)

    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="No puedes rechazar tu propia cuenta")

    with ctx.database.connect() as db:
        begin_write(db)
        try:
            ensure_not_last_admin(db, user_id)
        except LastAdminError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not reject_user(db, user_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        revoked = revoke_user_sessions(db, user_id)
        record_event(
            db,
            "admin.user_reject",
            "success",
            actor_user_id=admin["id"],
            target_type="user",
            target_id=user_id,
            ip=client_ip(request),
            details={"sessions_revoked": revoked},
        )

    return {"updated": True, "approval_status": "rejected", "is_active": False}


@router.patch("/users/{user_id}/active")
def admin_set_user_active(
    user_id: str, request: Request, payload: UserActiveRequest, admin: AdminUser, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)

    if user_id == admin["id"] and not payload.active:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    with ctx.database.connect() as db:
        begin_write(db)
        if not payload.active:
            try:
                ensure_not_last_admin(db, user_id)
            except LastAdminError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not set_user_active(db, user_id, payload.active):
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        revoked = 0 if payload.active else revoke_user_sessions(db, user_id)
        record_event(
            db,
            "admin.user_activate" if payload.active else "admin.user_deactivate",
            "success",
            actor_user_id=admin["id"],
            target_type="user",
            target_id=user_id,
            ip=client_ip(request),
            details={"sessions_revoked": revoked},
        )

    return {"updated": True, "is_active": payload.active}


@router.patch("/settings/registration")
def admin_set_registration(
    request: Request, payload: RegistrationSettingRequest, admin: AdminUser, ctx: Ctx
) -> dict[str, Any]:
    validate_origin(request, ctx)

    with ctx.database.connect() as db:
        set_registration_enabled(db, payload.enabled)
        record_event(
            db,
            "admin.registration_toggle",
            "success",
            actor_user_id=admin["id"],
            ip=client_ip(request),
            details={"enabled": payload.enabled},
        )

    return {"updated": True, "public_registration_enabled": payload.enabled}


@router.get("/audit")
def admin_audit(
    admin: AdminUser, ctx: Ctx, limit: int = 100, action: str | None = None
) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {"events": list_events(db, limit=limit, action=action)}


@router.get("/security")
def admin_security(admin: AdminUser, ctx: Ctx, days: int = 14) -> dict[str, Any]:
    """Resumen de seguridad derivado de la auditoría (solo administradores de plataforma)."""
    days = min(max(days, 1), 90)
    with ctx.database.connect() as db:
        return {"days": days, **security_summary(db, days=days)}


@router.get("/usage")
def admin_usage(admin: AdminUser, ctx: Ctx, days: int = 30) -> dict[str, Any]:
    store = UsageStore(ctx.database)
    return {
        "usage": store.summary(min(max(days, 1), 365)),
        "month_cost_usd": store.month_cost_usd(),
    }
