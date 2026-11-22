import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from nexaro_api.deps import (
    AdminUser,
    Ctx,
    CurrentUser,
    OrgAccess,
    client_ip,
    require_permission,
    validate_origin,
)
from nexaro_api.schemas import MemberAddRequest, MemberRoleRequest, OrganizationCreateRequest
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from nexaro_core.organizations import (
    AlreadyMemberError,
    LastOwnerError,
    MemberNotFoundError,
    OrganizationError,
    RoleChangeNotAllowedError,
    SlugTakenError,
    UserNotFoundError,
    add_member,
    create_organization,
    list_members,
    list_user_organizations,
    remove_member,
    set_member_role,
)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

CanReadMembers = Annotated[OrgAccess, Depends(require_permission("members:read"))]
CanManageMembers = Annotated[OrgAccess, Depends(require_permission("members:manage"))]

_STATUS = {
    SlugTakenError: 409,
    AlreadyMemberError: 409,
    UserNotFoundError: 404,
    MemberNotFoundError: 404,
    LastOwnerError: 400,
    RoleChangeNotAllowedError: 403,
}


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(type(exc), 400), detail=str(exc))


@router.post("", status_code=201)
def create(
    request: Request, body: OrganizationCreateRequest, admin: AdminUser, ctx: Ctx
) -> dict[str, Any]:
    """ASSUMPTION: solo los administradores de la plataforma crean organizaciones."""
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            organization = create_organization(db, body.name, body.slug, admin["id"])
        except OrganizationError as exc:
            raise _http(exc) from exc
        record_event(
            db,
            "org.create",
            "success",
            actor_user_id=admin["id"],
            target_type="organization",
            target_id=organization["id"],
            ip=client_ip(request),
        )
    return organization


@router.get("")
def mine(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {"organizations": list_user_organizations(db, user["id"])}


@router.get("/{organization_id}/members")
def members(organization_id: str, access: CanReadMembers, ctx: Ctx) -> dict[str, Any]:
    with ctx.database.connect() as db:
        return {"members": list_members(db, organization_id)}


def _mutate(
    action: str,
    organization_id: str,
    target_user_id: str | None,
    request: Request,
    access: OrgAccess,
    ctx: Any,
    operation: Any,
) -> Any:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            result = operation(db)
        except OrganizationError as exc:
            raise _http(exc) from exc
        except sqlite3.IntegrityError as exc:  # no debería ocurrir: se valida antes
            raise HTTPException(status_code=409, detail="Conflicto de datos") from exc
        record_event(
            db,
            action,
            "success",
            actor_user_id=access.user["id"],
            target_type="organization",
            target_id=organization_id,
            ip=client_ip(request),
            details={"member": target_user_id} if target_user_id else None,
        )
    return result


@router.post("/{organization_id}/members", status_code=201)
def add(
    organization_id: str,
    body: MemberAddRequest,
    request: Request,
    access: CanManageMembers,
    ctx: Ctx,
) -> dict[str, Any]:
    result: dict[str, Any] = _mutate(
        "org.member_add",
        organization_id,
        None,
        request,
        access,
        ctx,
        lambda db: add_member(db, organization_id, body.email, body.role, access.membership.role),
    )
    return result


@router.patch("/{organization_id}/members/{user_id}")
def change_role(
    organization_id: str,
    user_id: str,
    body: MemberRoleRequest,
    request: Request,
    access: CanManageMembers,
    ctx: Ctx,
) -> dict[str, Any]:
    _mutate(
        "org.member_role",
        organization_id,
        user_id,
        request,
        access,
        ctx,
        lambda db: set_member_role(db, organization_id, user_id, body.role, access.membership.role),
    )
    return {"updated": True, "role": body.role}


@router.delete("/{organization_id}/members/{user_id}")
def remove(
    organization_id: str, user_id: str, request: Request, access: CanManageMembers, ctx: Ctx
) -> dict[str, Any]:
    _mutate(
        "org.member_remove",
        organization_id,
        user_id,
        request,
        access,
        ctx,
        lambda db: remove_member(db, organization_id, user_id, access.membership.role),
    )
    return {"removed": True}
