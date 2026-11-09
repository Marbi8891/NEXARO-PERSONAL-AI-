"""Módulo Finance, gastos: registro, resumen mensual y exportación CSV (ADR-0013)."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from nexaro_api.deps import Ctx, OrgAccess, client_ip, require_permission, validate_origin
from nexaro_api.schemas import ExpenseCreateRequest, ExpenseUpdateRequest
from nexaro_core.audit import record_event
from nexaro_core.database import begin_write
from products.finance import expenses as svc

router = APIRouter(prefix="/api/organizations/{organization_id}/expenses", tags=["finance"])

CanRead = Annotated[OrgAccess, Depends(require_permission("expenses:read"))]
CanWrite = Annotated[OrgAccess, Depends(require_permission("expenses:write"))]
NOT_FOUND = HTTPException(status_code=404, detail="Gasto no encontrado")


def _invalid(exc: svc.ExpenseError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("")
def list_all(
    organization_id: str,
    access: CanRead,
    ctx: Ctx,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        with ctx.database.connect() as db:
            result = svc.list_expenses(
                db,
                organization_id,
                start=start,
                end=end,
                category=category,
                query=q,
                limit=limit,
                offset=offset,
            )
            result["categories"] = svc.categories(db, organization_id)
    except svc.ExpenseError as exc:
        raise _invalid(exc) from exc
    return result


@router.get("/summary")
def summary(
    organization_id: str, access: CanRead, ctx: Ctx, month: str | None = None
) -> dict[str, Any]:
    try:
        chosen = date.fromisoformat(f"{month}-01") if month else date.today()
    except ValueError:
        raise HTTPException(
            status_code=422, detail="El mes debe tener el formato AAAA-MM"
        ) from None
    with ctx.database.connect() as db:
        return svc.summary(db, organization_id, chosen)


@router.get("/export.csv")
def export(
    organization_id: str,
    request: Request,
    access: CanRead,
    ctx: Ctx,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
) -> Response:
    try:
        with ctx.database.connect() as db:
            content = svc.export_csv(db, organization_id, start=start, end=end, category=category)
            record_event(
                db,
                "expense.export",
                "success",
                actor_user_id=access.user["id"],
                target_type="organization",
                target_id=organization_id,
                ip=client_ip(request),
            )
    except svc.ExpenseError as exc:
        raise _invalid(exc) from exc
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="gastos.csv"'},
    )


@router.post("", status_code=201)
def create(
    organization_id: str,
    body: ExpenseCreateRequest,
    request: Request,
    access: CanWrite,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            created = svc.create_expense(
                db, organization_id, access.user["id"], **body.model_dump()
            )
        except svc.ExpenseError as exc:
            raise _invalid(exc) from exc
        record_event(
            db,
            "expense.create",
            "success",
            actor_user_id=access.user["id"],
            target_type="expense",
            target_id=created["id"],
            ip=client_ip(request),
            details={"organization": organization_id},
        )
    return created


@router.patch("/{expense_id}")
def update(
    organization_id: str,
    expense_id: str,
    body: ExpenseUpdateRequest,
    request: Request,
    access: CanWrite,
    ctx: Ctx,
) -> dict[str, Any]:
    validate_origin(request, ctx)
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(v is None for k, v in changes.items() if k != "vendor"):
        raise HTTPException(status_code=422, detail="Indica al menos un campo válido")
    with ctx.database.connect() as db:
        begin_write(db)
        try:
            updated = svc.update_expense(db, organization_id, expense_id, changes)
        except svc.ExpenseError as exc:
            raise _invalid(exc) from exc
        if updated is None:
            raise NOT_FOUND
        record_event(
            db,
            "expense.update",
            "success",
            actor_user_id=access.user["id"],
            target_type="expense",
            target_id=expense_id,
            ip=client_ip(request),
            details={"organization": organization_id, "fields": sorted(changes)},
        )
    return updated


@router.delete("/{expense_id}", status_code=204)
def delete(
    organization_id: str, expense_id: str, request: Request, access: CanWrite, ctx: Ctx
) -> None:
    validate_origin(request, ctx)
    with ctx.database.connect() as db:
        begin_write(db)
        if not svc.delete_expense(db, organization_id, expense_id):
            raise NOT_FOUND
        record_event(
            db,
            "expense.delete",
            "success",
            actor_user_id=access.user["id"],
            target_type="expense",
            target_id=expense_id,
            ip=client_ip(request),
            details={"organization": organization_id},
        )
