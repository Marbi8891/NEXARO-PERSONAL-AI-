"""Series diarias sin huecos: los días sin datos valen 0 (un hueco no es un valor desconocido)."""

from datetime import date, datetime, timedelta, timezone
from typing import Any


def last_days(count: int, today: date | None = None) -> list[str]:
    """Últimos `count` días en UTC, en orden ascendente y terminando hoy (ISO 8601)."""
    end = today or datetime.now(timezone.utc).date()
    return [(end - timedelta(days=offset)).isoformat() for offset in range(count - 1, -1, -1)]


def fill_days(days: list[str], counts: dict[str, int], key: str) -> list[dict[str, Any]]:
    return [{"date": day, key: counts.get(day, 0)} for day in days]
