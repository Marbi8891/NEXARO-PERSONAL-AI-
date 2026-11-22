from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from nexaro_api.context import AppContext
from nexaro_core.api_keys import ApiKeyIdentity, authenticate_api_key
from nexaro_core.audit import record_event
from nexaro_core.identity import get_session_user
from nexaro_core.organizations import Membership, get_membership, has_permission
from nexaro_core.security import Lease, TooBusy


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


def acquire_generation(ctx: AppContext, key: str, *, rate_limit: bool = True) -> Lease:
    """Hueco para una generación. 429 si el usuario va demasiado rápido o tiene demasiadas abiertas;
    503 si el modelo está saturado. Hay que llamar a `lease.release()` al terminar."""
    if rate_limit:
        if ctx.chat_limiter.is_limited(key):
            raise HTTPException(
                status_code=429,
                detail="Demasiadas peticiones al modelo. Espera un momento.",
                headers={"Retry-After": "30"},
            )
        ctx.chat_limiter.record(key)
    try:
        return ctx.chat_guard.acquire(key)
    except TooBusy as busy:
        if busy.scope == "user":
            raise HTTPException(
                status_code=429,
                detail="Ya tienes respuestas en curso. Espera a que terminen.",
                headers={"Retry-After": "5"},
            ) from None
        raise HTTPException(
            status_code=503,
            detail="El modelo está ocupado. Inténtalo de nuevo en unos segundos.",
            headers={"Retry-After": "10"},
        ) from None


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


@dataclass(frozen=True)
class OrgAccess:
    user: dict[str, Any]
    membership: Membership


def check_org_permission(
    ctx: AppContext, request: Request, user: dict[str, Any], organization_id: str, permission: str
) -> OrgAccess:
    """Membresía activa + permiso. No ser miembro es un 404 (no se revela que la organización
    existe). Ser administrador de la plataforma NO da acceso."""
    denied = False
    with ctx.database.connect() as db:
        membership = get_membership(db, user["id"], organization_id)
        if membership is not None and not has_permission(db, membership, permission):
            denied = True  # se lanza fuera del `with`: la auditoría no debe revertirse
            record_event(
                db,
                "authz.permission_denied",
                "denied",
                actor_user_id=user["id"],
                target_type="organization",
                target_id=organization_id,
                ip=client_ip(request),
                details={"permission": permission, "path": request.url.path},
            )
    if membership is None:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    if denied:
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    return OrgAccess(user=user, membership=membership)


def require_permission(permission: str) -> Callable[..., OrgAccess]:
    """Dependencia de FastAPI para rutas /organizations/{organization_id}/..."""

    def dependency(
        organization_id: str, request: Request, ctx: Ctx, user: CurrentUser
    ) -> OrgAccess:
        return check_org_permission(ctx, request, user, organization_id, permission)

    return dependency


def get_api_key_identity(request: Request, ctx: Ctx) -> ApiKeyIdentity:
    """Autenticación por clave de API (`Authorization: Bearer nxr_...`) para /api/v1.

    No usa cookies ni exige Origin (no hay navegador). Los fallos se limitan por IP y no
    distinguen si la clave no existe, caducó o fue revocada."""
    ip = f"apikey-ip:{client_ip(request)}"
    if ctx.limiter.is_limited(ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos. Inténtalo más tarde.")
    scheme, _, secret = request.headers.get("authorization", "").partition(" ")
    identity = None
    if scheme.lower() == "bearer" and secret:
        with ctx.database.connect() as db:
            identity = authenticate_api_key(db, secret.strip())
    if identity is None:
        ctx.limiter.record(ip)
        raise HTTPException(
            status_code=401,
            detail="Clave de API no válida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


def require_scope(scope: str) -> Callable[..., ApiKeyIdentity]:
    """Clave válida con el permiso indicado y dentro de su límite por minuto (429 si lo supera)."""

    def dependency(
        ctx: Ctx, identity: Annotated[ApiKeyIdentity, Depends(get_api_key_identity)]
    ) -> ApiKeyIdentity:
        if not identity.allows(scope):
            raise HTTPException(status_code=403, detail=f"La clave no tiene el permiso {scope}")
        if ctx.key_limiter.is_limited(identity.key_id):
            raise HTTPException(
                status_code=429,
                detail="Límite de peticiones por minuto superado",
                headers={"Retry-After": "60"},
            )
        ctx.key_limiter.record(identity.key_id)
        return identity

    return dependency


ChatKey = Annotated[ApiKeyIdentity, Depends(require_scope("chat:write"))]
ReadKey = Annotated[ApiKeyIdentity, Depends(require_scope("conversations:read"))]
