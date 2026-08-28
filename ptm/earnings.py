"""Resolving the next earnings date, including when nobody publishes one.

Distances are CALENDAR days, matching both the earnings buckets and the PTM
catalyst window (30-90 calendar days = the process's 20-60 trading days).

Yahoo's calendar often carries no future date — the last one has passed and the
next has not been scheduled. Rather than drop those names into a junk folder,
the next report is projected deterministically from the company's own filing
cadence, and the projection is stated in full wherever it is used.

Since fundamentals come from EDGAR alone, and EDGAR publishes no forward
earnings calendar, **every** date here is a projection - there is no "confirmed"
alternative to fall back on. The catalyst gate therefore runs on projected
dates, which is a real limitation and is stated on every idea rather than
hidden: `estimated` is always true and `basis` spells out the last report and
the cadence used. Treat a name sitting near a window boundary as uncertain.
"""

from __future__ import annotations

from datetime import date, timedelta

from ptm.asof import as_of_date, days_until, parse_day
from ptm.models import EarningsEstimate
from ptm.risk import normalize_earnings_date

# US issuers report quarterly; ~91 calendar days is the default step when a
# company has too little filing history to measure its own cadence.
DEFAULT_CADENCE_DAYS = 91
MIN_CADENCE_DAYS = 45
MAX_CADENCE_DAYS = 200


def _cadence_from(dates: list[date]) -> tuple[int, int]:
    """(median-ish cadence in days, number of gaps used)."""
    gaps = [(dates[i] - dates[i + 1]).days for i in range(min(len(dates) - 1, 4))]
    gaps = [g for g in gaps if MIN_CADENCE_DAYS <= g <= MAX_CADENCE_DAYS]
    if not gaps:
        return DEFAULT_CADENCE_DAYS, 0
    return round(sum(gaps) / len(gaps)), len(gaps)


def _roll_forward(anchor: date, cadence: int, ref: date) -> date:
    nxt = anchor + timedelta(days=cadence)
    guard = 0
    while nxt <= ref and guard < 12:
        nxt += timedelta(days=cadence)
        guard += 1
    return nxt


def resolve(
    ticker: str,
    raw_date: object | None,
    ref: date | None = None,
    report_dates: list[str] | None = None,
) -> EarningsEstimate:
    """Work out the date this idea should be filed under.

    `report_dates` are past 10-K/10-Q filing dates, newest first. When omitted
    they are fetched from EDGAR (cached, and bounded by the run date).
    """
    ref = ref or as_of_date()
    published = normalize_earnings_date(raw_date)

    if published:
        try:
            when = parse_day(published)
        except ValueError:
            when = None
        if when and when > ref:
            return EarningsEstimate(
                ticker=ticker,
                date=published,
                estimated=False,
                days_to_earnings=days_until(when.isoformat(), ref=ref),
                basis=f"published earnings date {published}",
            )

    if report_dates is None:
        try:
            from ptm.ingest.edgar import report_dates as edgar_report_dates

            report_dates = edgar_report_dates(ticker)
        except Exception:
            report_dates = []

    parsed: list[date] = []
    for item in report_dates or []:
        try:
            day = parse_day(item)
        except ValueError:
            continue
        if day <= ref:
            parsed.append(day)
    parsed = sorted(set(parsed), reverse=True)

    # A published-but-past date is itself evidence of when they last reported.
    if published:
        try:
            past = parse_day(published)
            if past <= ref and past not in parsed:
                parsed = sorted(set(parsed + [past]), reverse=True)
        except ValueError:
            pass

    if parsed:
        cadence, used = _cadence_from(parsed)
        last = parsed[0]
        projected = _roll_forward(last, cadence, ref)
        cadence_note = (
            f"{cadence}-day cadence measured over {used} prior gaps"
            if used
            else f"assumed {cadence}-day quarterly cadence (too few filings to measure)"
        )
        return EarningsEstimate(
            ticker=ticker,
            date=projected.isoformat(),
            estimated=True,
            last_report=last.isoformat(),
            cadence_days=cadence,
            days_to_earnings=days_until(projected.isoformat(), ref=ref),
            basis=(
                f"no future earnings date published; last reported {last.isoformat()}, "
                f"so the next report is estimated {projected.isoformat()} ({cadence_note})"
            ),
        )

    # Nothing at all to anchor on: assume a quarter from the run date and say so.
    projected = ref + timedelta(days=DEFAULT_CADENCE_DAYS)
    return EarningsEstimate(
        ticker=ticker,
        date=projected.isoformat(),
        estimated=True,
        last_report=None,
        cadence_days=DEFAULT_CADENCE_DAYS,
        days_to_earnings=days_until(projected.isoformat(), ref=ref),
        basis=(
            "no earnings date published and no prior filings found; assumed one quarter "
            f"from the run date, estimated {projected.isoformat()}"
        ),
    )


def sentence(estimate: EarningsEstimate, bucket: str) -> str:
    """The one-line statement that travels with an estimated date."""
    if not estimate.estimated:
        return f"Earnings {estimate.date} ({estimate.days_to_earnings} calendar days) → {bucket}."
    return f"{estimate.basis}, which places it {estimate.days_to_earnings} calendar days out → {bucket}."
