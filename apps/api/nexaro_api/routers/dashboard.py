from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from ai_gateway.usage import UsageStore
from nexaro_api.deps import Ctx, CurrentUser
from nexaro_api.notifications import (
    FAILED_LOGIN_THRESHOLD,
    FAILED_LOGIN_WINDOW_MINUTES,
    build_notifications,
)
from nexaro_core.audit import count_events
from nexaro_core.identity import get_registration_enabled, user_counts
from nexaro_core.timeseries import fill_days, last_days

router = APIRouter(prefix="/api", tags=["dashboard"])

MAX_DAYS = 90
DAY_MINUTES = 24 * 60


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/dashboard")
def dashboard(user: CurrentUser, ctx: Ctx, days: int = 14) -> dict[str, Any]:
    days = min(max(days, 1), MAX_DAYS)
    admin_section: dict[str, Any] | None = None

    if user["role"] == "admin":
        window = last_days(days)
        store = UsageStore(ctx.database)
        per_day = store.daily(days)
        with ctx.database.connect() as db:
            users = user_counts(db)
            failed = count_events(
                db, action="auth.login", outcome="failure", since_minutes=DAY_MINUTES
            )
            denied = sum(
                count_events(db, action=action, outcome="denied", since_minutes=DAY_MINUTES)
                for action in _denied_actions(db)
            )
        requests = {row["day"]: int(row["requests"]) for row in per_day}
        errors = {row["day"]: int(row["errors"]) for row in per_day}
        admin_section = {
            "users": users,
            "usage": {
                "month_cost_usd": store.month_cost_usd(),
                "requests_period": sum(requests.values()),
                "daily": [
                    {
                        "date": r["date"],
                        "requests": r["requests"],
                        "errors": errors.get(r["date"], 0),
                    }
                    for r in fill_days(window, requests, "requests")
                ],
            },
            "security": {"failed_logins_24h": failed, "denied_24h": denied},
        }

    return {
        "generated_at": _now(),
        "days": days,
        "activity": ctx.personal_ai.activity(user["id"], days),
        "admin": admin_section,
    }


def _denied_actions(db: Any) -> list[str]:
    rows = db.execute(
        """
        SELECT DISTINCT action FROM audit_events
        WHERE outcome = 'denied'
          AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day')
        """
    ).fetchall()
    return [row["action"] for row in rows]


@router.get("/notifications")
async def notifications(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    is_admin = user["role"] == "admin"
    model_available = await ctx.provider.health()
    pending = failed = 0
    registration_open = False
    if is_admin:
        with ctx.database.connect() as db:
            pending = user_counts(db)["pending"]
            failed = count_events(
                db,
                action="auth.login",
                outcome="failure",
                since_minutes=FAILED_LOGIN_WINDOW_MINUTES,
            )
            registration_open = get_registration_enabled(db)
    return {
        "generated_at": _now(),
        "threshold": FAILED_LOGIN_THRESHOLD,
        "notifications": build_notifications(
            model_available=model_available,
            is_admin=is_admin,
            pending_approvals=pending,
            failed_logins=failed,
            registration_open=registration_open,
        ),
    }
