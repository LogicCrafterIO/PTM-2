"""Run-date helpers for backdated runs.

Pricing a name at the run date's close, and projecting its next report from
past filing cadence rather than a vendor calendar. The fundamentals table
itself is built in ptm/fundamentals.py, from EDGAR, for every run.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ptm.asof import as_of_date

# Median US large-cap reporting gap; used only to project the next report date.
QUARTER_DAYS = 91


def close_on(prices: pd.DataFrame, ticker: str, upto: date) -> float | None:
    """Last close at or before the run date."""
    if prices is None or prices.empty:
        return None
    frame = prices
    if "ticker" not in frame.columns or "close" not in frame.columns:
        return None
    sub = frame[frame["ticker"] == ticker]
    if sub.empty:
        return None
    date_col = "date" if "date" in sub.columns else ("datetime" if "datetime" in sub.columns else None)
    if date_col:
        sub = sub.copy()
        sub["_d"] = pd.to_datetime(sub[date_col], errors="coerce", utc=True)
        cutoff = pd.Timestamp(upto, tz="UTC") + pd.Timedelta(hours=23, minutes=59)
        sub = sub.dropna(subset=["_d"]).sort_values("_d")
        sub = sub[sub["_d"] <= cutoff]
    closes = pd.to_numeric(sub["close"], errors="coerce").dropna()
    return float(closes.iloc[-1]) if len(closes) else None


def next_report_estimate(report_dates: list[str], upto: date) -> tuple[str | None, str]:
    """Project the next earnings date from past filing cadence.

    Deliberately does not consult Yahoo's calendar: that returns the currently
    scheduled date, which on a backdated run is knowledge from the future.
    """
    if not report_dates:
        return None, "no filing history"
    try:
        parsed = sorted({date.fromisoformat(str(d)[:10]) for d in report_dates}, reverse=True)
    except ValueError:
        return None, "unparseable filing dates"
    past = [d for d in parsed if d <= upto]
    if not past:
        return None, "no filings before the run date"
    gaps = [(past[i] - past[i + 1]).days for i in range(min(len(past) - 1, 4))]
    gaps = [g for g in gaps if 45 <= g <= 200]
    cadence = round(sum(gaps) / len(gaps)) if gaps else QUARTER_DAYS
    nxt = past[0] + timedelta(days=cadence)
    guard = 0
    while nxt <= upto and guard < 8:
        nxt += timedelta(days=cadence)
        guard += 1
    return nxt.isoformat(), f"projected from {len(past)} filings, {cadence}d cadence"


def coverage_warnings(frame: pd.DataFrame) -> list[str]:
    """Honest caveats to attach to any backdated run summary."""
    warnings = [
        "BACKDATED RUN: forward EPS is company guidance where the 8-K earnings release "
        "carried it, otherwise extrapolated realized growth. Neither is the analyst "
        "consensus that existed on the run date (no free point-in-time source). "
        "Trailing P/E, by contrast, is exact: as-of close over EPS from filings public that day.",
        "BACKDATED RUN: index membership comes from today's Wikipedia lists, so the "
        "universe carries survivorship and membership drift.",
        "BACKDATED RUN: the next-earnings date is projected from filing cadence, not "
        "the calendar as published then.",
    ]
    if frame is None or frame.empty:
        warnings.append("BACKDATED RUN: no point-in-time fundamentals were rebuilt.")
        return warnings
    total = len(frame)
    if "forward_eps" in frame.columns:
        have = int(frame["forward_eps"].notna().sum())
        if have < 0.6 * total:
            warnings.append(
                f"BACKDATED RUN: only {have}/{total} names had EPS filings visible on the "
                "run date; the PE screen is thinner than a live run."
            )
    if "pit_forward_source" in frame.columns:
        counts = frame["pit_forward_source"].value_counts().to_dict()
        guided = int(counts.get("management_guidance", 0))
        warnings.append(
            f"BACKDATED RUN: forward EPS sources — {guided} from company guidance, "
            f"{int(counts.get('extrapolated', 0))} extrapolated, {int(counts.get('flat', 0))} held flat."
        )
    if "price" in frame.columns:
        priced = int(frame["price"].notna().sum())
        if priced < 0.9 * total:
            warnings.append(f"BACKDATED RUN: only {priced}/{total} names had a close on the run date.")
    return warnings
