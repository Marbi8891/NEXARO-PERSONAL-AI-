from datetime import date

from nexaro_core.timeseries import fill_days, last_days


def test_last_days_ends_today_and_is_ascending() -> None:
    days = last_days(3, today=date(2026, 11, 9))
    assert days == ["2026-11-07", "2026-11-08", "2026-11-09"]


def test_last_days_crosses_month_and_year() -> None:
    assert last_days(3, today=date(2027, 1, 1)) == ["2026-12-30", "2026-12-31", "2027-01-01"]


def test_fill_days_adds_zeros_for_missing_days() -> None:
    result = fill_days(["2026-11-08", "2026-11-09"], {"2026-11-09": 4}, "messages")
    assert result == [
        {"date": "2026-11-08", "messages": 0},
        {"date": "2026-11-09", "messages": 4},
    ]


def test_fill_days_ignores_days_outside_the_window() -> None:
    assert fill_days(["2026-11-09"], {"2020-01-01": 99}, "n") == [{"date": "2026-11-09", "n": 0}]
