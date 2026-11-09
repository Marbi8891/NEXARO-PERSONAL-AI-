"""Gastos de una organización (ADR-0013). Importes en céntimos; moneda única: EUR."""

import csv
import io
import sqlite3
import uuid
from datetime import date, timedelta
from typing import Any

MAX_AMOUNT_CENTS = 100_000_000  # 1 000 000 €
MIN_DATE = date(2000, 1, 1)
MAX_LIMIT = 200
CSV_COLUMNS = ("fecha", "descripcion", "proveedor", "categoria", "importe_eur", "iva_eur")
_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


class ExpenseError(Exception):
    pass


def normalize_category(value: str) -> str:
    category = " ".join(value.split()).lower()
    if not 1 <= len(category) <= 40:
        raise ExpenseError("La categoría debe tener entre 1 y 40 caracteres")
    return category


def _validate(spent_on: date, amount_cents: int, vat_cents: int) -> None:
    if spent_on < MIN_DATE or spent_on > date.today() + timedelta(days=1):
        raise ExpenseError("La fecha debe estar entre 2000-01-01 y hoy")
    if not 0 < amount_cents <= MAX_AMOUNT_CENTS:
        raise ExpenseError("El importe debe ser mayor que 0 y como máximo 1.000.000 €")
    if not 0 <= vat_cents <= amount_cents:
        raise ExpenseError("El IVA no puede ser negativo ni superar el importe")


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "spent_on": row["spent_on"],
        "description": row["description"],
        "vendor": row["vendor"],
        "category": row["category"],
        "amount_cents": row["amount_cents"],
        "vat_cents": row["vat_cents"],
        "currency": row["currency"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_expense(
    db: sqlite3.Connection,
    organization_id: str,
    created_by: str,
    *,
    spent_on: date,
    description: str,
    amount_cents: int,
    category: str,
    vat_cents: int = 0,
    vendor: str | None = None,
) -> dict[str, Any]:
    """Debe llamarse dentro de una transacción de escritura."""
    _validate(spent_on, amount_cents, vat_cents)
    expense_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO expenses (id, organization_id, spent_on, description, vendor, category,
                              amount_cents, vat_cents, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            expense_id,
            organization_id,
            spent_on.isoformat(),
            description.strip(),
            (vendor or "").strip() or None,
            normalize_category(category),
            amount_cents,
            vat_cents,
            created_by,
        ),
    )
    return _public(db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone())


def update_expense(
    db: sqlite3.Connection, organization_id: str, expense_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    """Actualización parcial. None si no existe (o está borrado) en esa organización."""
    row = db.execute(
        "SELECT * FROM expenses WHERE id = ? AND organization_id = ? AND deleted_at IS NULL",
        (expense_id, organization_id),
    ).fetchone()
    if row is None:
        return None
    merged = {**_public(row), **changes}
    spent_on = merged["spent_on"]
    if isinstance(spent_on, str):
        spent_on = date.fromisoformat(spent_on)
    _validate(spent_on, merged["amount_cents"], merged["vat_cents"])
    db.execute(
        """
        UPDATE expenses SET spent_on = ?, description = ?, vendor = ?, category = ?,
               amount_cents = ?, vat_cents = ?, updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
        WHERE id = ?
        """,
        (
            spent_on.isoformat(),
            str(merged["description"]).strip(),
            (merged["vendor"] or "").strip() or None,
            normalize_category(merged["category"]),
            merged["amount_cents"],
            merged["vat_cents"],
            expense_id,
        ),
    )
    return _public(db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone())


def delete_expense(db: sqlite3.Connection, organization_id: str, expense_id: str) -> bool:
    cursor = db.execute(
        """
        UPDATE expenses SET deleted_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
        WHERE id = ? AND organization_id = ? AND deleted_at IS NULL
        """,
        (expense_id, organization_id),
    )
    return cursor.rowcount == 1


def _filters(
    organization_id: str,
    start: date | None,
    end: date | None,
    category: str | None,
    query: str | None,
) -> tuple[str, list[Any]]:
    where = ["organization_id = ?", "deleted_at IS NULL"]
    args: list[Any] = [organization_id]
    if start:
        where.append("spent_on >= ?")
        args.append(start.isoformat())
    if end:
        where.append("spent_on <= ?")
        args.append(end.isoformat())
    if category:
        where.append("category = ?")
        args.append(normalize_category(category))
    if query and query.strip():
        like = f"%{query.strip().lower()}%"
        where.append("(lower(description) LIKE ? OR lower(COALESCE(vendor, '')) LIKE ?)")
        args += [like, like]
    return " AND ".join(where), args


def list_expenses(
    db: sqlite3.Connection,
    organization_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    where, args = _filters(organization_id, start, end, category, query)
    totals = db.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS cents, "  # noqa: S608
        f"COALESCE(SUM(vat_cents), 0) AS vat FROM expenses WHERE {where}",
        args,
    ).fetchone()
    rows = db.execute(
        f"SELECT * FROM expenses WHERE {where} "  # noqa: S608
        "ORDER BY spent_on DESC, created_at DESC, rowid DESC LIMIT ? OFFSET ?",
        [*args, min(max(limit, 1), MAX_LIMIT), max(offset, 0)],
    ).fetchall()
    return {
        "expenses": [_public(r) for r in rows],
        "total": totals["n"],
        "total_cents": totals["cents"],
        "total_vat_cents": totals["vat"],
    }


def categories(db: sqlite3.Connection, organization_id: str) -> list[str]:
    rows = db.execute(
        "SELECT DISTINCT category FROM expenses WHERE organization_id = ? AND deleted_at IS NULL "
        "ORDER BY category",
        (organization_id,),
    ).fetchall()
    return [r["category"] for r in rows]


def _month_start(day: date, back: int = 0) -> date:
    index = day.year * 12 + day.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def summary(
    db: sqlite3.Connection, organization_id: str, month: date, history: int = 6
) -> dict[str, Any]:
    """Totales del mes, reparto por categoría y serie de los últimos `history` meses."""
    first = month.replace(day=1)
    following = _month_start(first, -1)
    base = "organization_id = ? AND deleted_at IS NULL"
    current = db.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS cents, "  # noqa: S608
        f"COALESCE(SUM(vat_cents), 0) AS vat FROM expenses "
        f"WHERE {base} AND spent_on >= ? AND spent_on < ?",
        (organization_id, first.isoformat(), following.isoformat()),
    ).fetchone()
    by_category = db.execute(
        f"SELECT category, SUM(amount_cents) AS cents, COUNT(*) AS n FROM expenses "  # noqa: S608
        f"WHERE {base} AND spent_on >= ? AND spent_on < ? "
        "GROUP BY category ORDER BY cents DESC, category",
        (organization_id, first.isoformat(), following.isoformat()),
    ).fetchall()
    months = [_month_start(first, back) for back in range(history - 1, -1, -1)]
    per_month = {
        r["month"]: r["cents"]
        for r in db.execute(
            f"SELECT substr(spent_on, 1, 7) AS month, SUM(amount_cents) AS cents FROM expenses "  # noqa: S608
            f"WHERE {base} AND spent_on >= ? AND spent_on < ? GROUP BY month",
            (organization_id, months[0].isoformat(), following.isoformat()),
        )
    }
    return {
        "month": first.strftime("%Y-%m"),
        "count": current["n"],
        "total_cents": current["cents"],
        "vat_cents": current["vat"],
        "by_category": [
            {"category": r["category"], "total_cents": r["cents"], "count": r["n"]}
            for r in by_category
        ],
        "history": [
            {"month": m.strftime("%Y-%m"), "total_cents": per_month.get(m.strftime("%Y-%m"), 0)}
            for m in months
        ],
    }


def _euros(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02d}"


def _safe(text: str | None) -> str:
    """Evita que Excel/Calc interprete una celda como fórmula (inyección CSV)."""
    value = text or ""
    return "'" + value if value.startswith(_FORMULA_CHARS) else value


def export_csv(
    db: sqlite3.Connection,
    organization_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
) -> str:
    """CSV para hoja de cálculo en español: separador `;`, coma decimal, BOM UTF-8."""
    where, args = _filters(organization_id, start, end, category, None)
    rows = db.execute(
        f"SELECT * FROM expenses WHERE {where} ORDER BY spent_on, created_at, rowid",  # noqa: S608
        args,
    ).fetchall()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        writer.writerow(
            [
                r["spent_on"],
                _safe(r["description"]),
                _safe(r["vendor"]),
                _safe(r["category"]),
                _euros(r["amount_cents"]),
                _euros(r["vat_cents"]),
            ]
        )
    return "﻿" + out.getvalue()
