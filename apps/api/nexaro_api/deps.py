from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from nexaro_api.context import AppContext
from nexaro_core.audit import record_event
from nexaro_core.identity import get_session_user


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def validate_origin(request: Request, ctx: AppContext) -> None:
    origin = request.headers.get("origin")
    if not origin or origin not in ctx.settings.allowed_origins:
        raise HTTPException(status_code=403, detail="Origen no permitido")


def get_current_user(request: Request, ctx: Ctx) -> dict[str, Any]:
    token = request.cookies.get(ctx.settings.cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Autenticación requerida")

    with ctx.database.connect() as db:
        user = get_session_user(db, token)

    if user is None:
        raise HTTPException(status_code=401, detail="Sesión no válida o caducada")

    return {"id": user["id"], "email": user["email"], "role": user["role"]}


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def get_admin_user(request: Request, ctx: Ctx, user: CurrentUser) -> dict[str, Any]:
    if user["role"] != "admin":
        with ctx.database.connect() as db:
            record_event(
                db,
                "authz.admin_required",
                "denied",
                actor_user_id=user["id"],
                ip=client_ip(request),
                details={"path": request.url.path, "method": request.method},
            )
        raise HTTPException(status_code=403, detail="Se requieren permisos de administrador")
    return user


AdminUser = Annotated[dict[str, Any], Depends(get_admin_user)]
