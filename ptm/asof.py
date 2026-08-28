"""Run-date context.

Every stage that asks "what is today?" asks here instead, so a backdated run
(`--as-of 2026-06-20`) sees the world as it looked on that date rather than now.

The binding constraint is ISM: ismworld.org only serves the last few monthly
PMI/Services reports at their `/<month>/` URLs, so a backdate is only honest as
far back as the oldest report still published. `validate_as_of` enforces that.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone

from ptm.config import toml_settings

_as_of: date | None = None


class AsOfUnavailable(ValueError):
    """Requested backdate predates the oldest ISM report still published."""


def _cfg() -> dict:
    return toml_settings().get("asof") or {}


def set_as_of(value: date | str | None) -> date | None:
    """Pin the run date. Pass None to restore real time (used by tests)."""
    global _as_of
    if value is None:
        _as_of = None
        return None
    _as_of = parse_day(value)
    return _as_of


def parse_day(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"as-of must be YYYY-MM-DD, got {value!r}") from exc


def real_today() -> date:
    """Wall-clock today, never the pinned date."""
    return datetime.now(timezone.utc).date()


def as_of_date() -> date:
    return _as_of or real_today()


def as_of_dt() -> datetime:
    """As-of as an aware UTC datetime at end of day, so same-day events count."""
    if _as_of is None:
        return datetime.now(timezone.utc)
    return datetime.combine(_as_of, time(23, 59, 59), tzinfo=timezone.utc)


def is_backdated() -> bool:
    return _as_of is not None and _as_of < real_today()


def day_slug() -> str:
    """Folder name for this run's ideas/ output."""
    return as_of_date().strftime("%Y-%m-%d")


def stamp() -> str:
    return as_of_dt().isoformat()


# --- ISM report availability -------------------------------------------------


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def ism_report_month(on: date | None = None) -> tuple[int, int]:
    """(year, month) of the newest ISM report released on or before `on`.

    ISM publishes month M's Manufacturing report on business day 1 of M+1 and
    Services on business day 3, so early in a month the prior month is not out
    yet and the newest available print is two months back.
    """
    on = on or as_of_date()
    release_day = int(_cfg().get("ism_release_day") or 4)
    delta = -1 if on.day >= release_day else -2
    return _shift_month(on.year, on.month, delta)


def ism_available_months(now: date | None = None) -> list[tuple[int, int]]:
    """Report months ismworld.org still serves, newest first."""
    now = now or real_today()
    depth = int(_cfg().get("ism_months_available") or 3)
    year, month = ism_report_month(now)
    return [_shift_month(year, month, -i) for i in range(depth)]


def month_slug(year_month: tuple[int, int]) -> str:
    return calendar.month_name[year_month[1]].lower()


def month_label(year_month: tuple[int, int]) -> str:
    return f"{calendar.month_name[year_month[1]]} {year_month[0]}"


def earliest_as_of(now: date | None = None) -> date:
    """Oldest date a backdated run can honestly claim ISM coverage for."""
    now = now or real_today()
    oldest = ism_available_months(now)[-1]
    release_day = int(_cfg().get("ism_release_day") or 4)
    year, month = _shift_month(oldest[0], oldest[1], 1)
    return date(year, month, release_day)


def validate_as_of(value: date | str, now: date | None = None) -> date:
    """Coerce and bounds-check a requested run date. Raises AsOfUnavailable."""
    now = now or real_today()
    day = parse_day(value)
    if day > now:
        raise AsOfUnavailable(f"as-of {day.isoformat()} is in the future (today is {now.isoformat()})")
    available = ism_available_months(now)
    wanted = ism_report_month(day)
    if wanted not in available:
        floor = earliest_as_of(now)
        have = ", ".join(month_label(m) for m in reversed(available))
        raise AsOfUnavailable(
            f"as-of {day.isoformat()} needs the {month_label(wanted)} ISM report, "
            f"but ismworld.org only still publishes {have}. "
            f"Earliest supported as-of is {floor.isoformat()}."
        )
    return day


def coverage() -> dict:
    """Machine-readable description of the current run date, for the audit."""
    now = real_today()
    day = as_of_date()
    report = ism_report_month(day)
    return {
        "as_of": day.isoformat(),
        "real_today": now.isoformat(),
        "backdated": is_backdated(),
        "ism_report_month": month_label(report),
        "ism_months_available": [month_label(m) for m in ism_available_months(now)],
        "earliest_as_of": earliest_as_of(now).isoformat(),
    }


def days_until(iso_date: str | None, ref: date | None = None) -> int | None:
    """Calendar days from the run date to an ISO date. Negative once past."""
    if not iso_date:
        return None
    try:
        target = parse_day(iso_date)
    except ValueError:
        return None
    return (target - (ref or as_of_date())).days


def quarters_back_to(iso_date: str | None, ref: date | None = None) -> str | None:
    """Step a known future earnings date back in ~91-day quarters until it is
    the next one after `ref`. Used to approximate the earnings date a backdated
    run would have seen; the true historical calendar is not on Yahoo."""
    if not iso_date:
        return None
    try:
        target = parse_day(iso_date)
    except ValueError:
        return None
    ref = ref or as_of_date()
    guard = 0
    while target - timedelta(days=91) > ref and guard < 12:
        target -= timedelta(days=91)
        guard += 1
    return target.isoformat()


# --- trading-day arithmetic --------------------------------------------------
# Earnings windows are counted in market sessions, not calendar days, so a
# 30-session window is ~6 calendar weeks and does not drift with weekends or
# holidays.


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm; Good Friday is two days earlier."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month = (h + lam - 7 * m + 114) // 31
    day = ((h + lam - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th `weekday` (Mon=0) of a month; n=-1 means the last one."""
    if n > 0:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + 7 * (n - 1))
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date | None:
    """NYSE moves a Saturday holiday to Friday and a Sunday one to Monday."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def nyse_holidays(year: int) -> set[date]:
    """Full-day NYSE closures. Half days are ignored: they are still sessions."""
    days: set[date] = set()
    # New Year's Day is the one exception: a Saturday 1 Jan is not observed.
    new_year = date(year, 1, 1)
    if new_year.weekday() == 6:
        days.add(date(year, 1, 2))
    elif new_year.weekday() != 5:
        days.add(new_year)
    days.add(_nth_weekday(year, 1, 0, 3))    # MLK
    days.add(_nth_weekday(year, 2, 0, 3))    # Washington's Birthday
    days.add(_easter(year) - timedelta(days=2))  # Good Friday
    days.add(_nth_weekday(year, 5, 0, -1))   # Memorial Day
    for fixed in (date(year, 6, 19), date(year, 7, 4), date(year, 12, 25)):
        observed = _observed(fixed)
        if observed:
            days.add(observed)
    days.add(_nth_weekday(year, 9, 0, 1))    # Labor Day
    days.add(_nth_weekday(year, 11, 3, 4))   # Thanksgiving
    return days


def _holiday_range(start: date, end: date) -> list[date]:
    days: set[date] = set()
    for year in range(min(start, end).year, max(start, end).year + 1):
        days |= nyse_holidays(year)
    return sorted(days)


def trading_days_between(start: date, end: date) -> int:
    """Market sessions from `start` (exclusive) to `end` (inclusive).

    Negative when `end` is in the past. Same day returns 0.
    """
    import numpy as np

    if start == end:
        return 0
    holidays = np.array(_holiday_range(start, end), dtype="datetime64[D]")
    if end > start:
        count = np.busday_count(
            np.datetime64(start + timedelta(days=1), "D"),
            np.datetime64(end + timedelta(days=1), "D"),
            holidays=holidays,
        )
        return int(count)
    count = np.busday_count(
        np.datetime64(end + timedelta(days=1), "D"),
        np.datetime64(start + timedelta(days=1), "D"),
        holidays=holidays,
    )
    return -int(count)


def trading_days_until(iso_date: str | None, ref: date | None = None) -> int | None:
    """Sessions from the run date to an ISO date. Negative once past."""
    if not iso_date:
        return None
    try:
        target = parse_day(iso_date)
    except ValueError:
        return None
    return trading_days_between(ref or as_of_date(), target)


def add_trading_days(start: date, sessions: int) -> date:
    """The date `sessions` market days after `start`."""
    import numpy as np

    holidays = np.array(
        _holiday_range(start, start + timedelta(days=int(sessions * 2) + 30)), dtype="datetime64[D]"
    )
    out = np.busday_offset(
        np.datetime64(start, "D"), sessions, roll="forward", holidays=holidays
    )
    return out.astype(date)
