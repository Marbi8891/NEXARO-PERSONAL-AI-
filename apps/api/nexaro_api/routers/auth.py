import sqlite3
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from nexaro_api.deps import Ctx, CurrentUser, client_ip, validate_origin
from nexaro_api.schemas import LoginRequest, RegisterRequest
from nexaro_core.audit import pseudonymize, record_event
from nexaro_core.identity import (
    authenticate,
    create_session,
    create_user,
    get_registration_enabled,
    get_session_user,
    revoke_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(request: Request, credentials: RegisterRequest, ctx: Ctx) -> dict[str, Any]:
    validate_origin(request, ctx)
    ip = client_ip(request)
    error: HTTPException | None = None
    user_id = ""

    # Los errores se lanzan DESPUÉS del bloque: lanzar dentro revertiría el evento de auditoría.
    with ctx.database.connect() as db:
        if not get_registration_enabled(db):
            record_event(db, "auth.register", "denied", ip=ip, details={"reason": "closed"})
            error = HTTPException(status_code=403, detail="El registro público está desactivado")
        else:
            try:
                user_id = create_user(db, credentials.email, credentials.password, approved=False)
            except ValueError as exc:
                error = HTTPException(status_code=400, detail=str(exc))
            except sqlite3.IntegrityError:
                error = HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")
            if error is None:
                record_event(
                    db, "auth.register", "success", target_type="user", target_id=user_id, ip=ip
                )
            else:
                record_event(
                    db, "auth.register", "failure", ip=ip, details={"status": error.status_code}
                )

    if error is not None:
        raise error

    return {
        "created": True,
        "user_id": user_id,
        "approval_status": "pending",
        "message": "La cuenta está pendiente de aprobación",
    }


@router.post("/login")
def login(request: Request, credentials: LoginRequest, ctx: Ctx) -> JSONResponse:
    # `def` (no `async def`): scrypt es CPU y bloquearía el event loop; así corre en el threadpool.
    validate_origin(request, ctx)
    ip = client_ip(request)
    email_ref = pseudonymize(credentials.email)
    ip_key, email_key = f"ip:{ip}", f"email:{credentials.email.strip().lower()}"
    limiter, ip_limiter = ctx.limiter, ctx.ip_limiter

    if ip_limiter.is_limited(ip_key) or limiter.is_limited(email_key):
        raise HTTPException(status_code=429, detail="Demasiados intentos. Inténtalo más tarde.")

    with ctx.database.connect() as db:
        user = authenticate(db, credentials.email, credentials.password)
        token = ""
        if user is None:
            record_event(db, "auth.login", "failure", target_id=email_ref, ip=ip)
        else:
            token = create_session(
                db, user["id"], lifetime=timedelta(seconds=ctx.settings.session_max_age_seconds)
            )
            record_event(db, "auth.login", "success", actor_user_id=user["id"], ip=ip)

    if user is None:
        ip_limiter.record(ip_key)
        limiter.record(email_key)
        if limiter.is_limited(email_key) or ip_limiter.is_limited(ip_key):
            # Una sola vez, al cruzar el umbral: evita que un ataque llene la auditoría.
            with ctx.database.connect() as db:
                record_event(db, "auth.lockout", "denied", target_id=email_ref, ip=ip)
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    # Solo se limpia el contador de la cuenta. Si un login válido reiniciara el de la IP,
    # quien tenga una cuenta propia podría intercalar accesos para seguir adivinando.
    limiter.clear(email_key)

    response = JSONResponse(
        {
            "authenticated": True,
            "user": {"id": user["id"], "email": user["email"], "role": user["role"]},
        }
    )
    response.set_cookie(
        key=ctx.settings.cookie_name,
        value=token,
        max_age=ctx.settings.session_max_age_seconds,
        httponly=True,
        secure=ctx.settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return {"authenticated": True, "user": user}


@router.post("/logout")
def logout(request: Request, ctx: Ctx) -> JSONResponse:
    validate_origin(request, ctx)
    token = request.cookies.get(ctx.settings.cookie_name)

    if token:
        with ctx.database.connect() as db:
            user = get_session_user(db, token)
            if revoke_session(db, token):
                record_event(
                    db,
                    "auth.logout",
                    "success",
                    actor_user_id=user["id"] if user else None,
                    ip=client_ip(request),
                )

    response = JSONResponse({"authenticated": False})
    response.delete_cookie(
        key=ctx.settings.cookie_name,
        path="/",
        httponly=True,
        secure=ctx.settings.cookie_secure,
        samesite="strict",
    )
    return response
