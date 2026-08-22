"""Beta, and the earnings-window helpers the catalyst gate runs on.

Two removals shaped this module. The SMA/EMA/MACD timing lights went first:
technical analysis takes no part in screening. The ATR stop, high-low range
target and R-score followed, once the book moved to options - a stop distance on
the underlying is not how a defined-risk position is managed, and the three
numbers gated nothing, ranked nothing and were rendered into a footnote nobody
read. The repository's own audit had said as much for months, via a
`timing.rscore_tautology` finding reading "R-score is currently a constant; it
cannot rank ideas".

What survives is load-bearing. `beta` drives beta-aware book selection in
ptm/book.py, and `earnings_in_window` / `catalyst_window` are half of the
process gate. Do not confuse those with the risk footnote that was removed.
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from ptm.asof import days_until
from ptm.config import toml_settings
from ptm.formulas import slope_beta
from ptm.models import Candidate, PRMResult


def _closes_from_prices(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    sub = prices[prices["ticker"] == ticker].copy()
    if sub.empty:
        return sub
    sub.columns = [str(c).lower() for c in sub.columns]
    date_col = "date" if "date" in sub.columns else "datetime"
    if date_col in sub.columns:
        sub = sub.sort_values(date_col)
    return sub


def prm_for(prices: pd.DataFrame, candidate: Candidate, market_closes: list[float] | None = None) -> PRMResult:
    """Beta against the index, from daily returns.

    OLS slope over at most 252 sessions. Returns None rather than a guess when
    either series is too short to mean anything; ptm/book.py then treats the
    name as beta 1.0 rather than pretending to know.
    """
    sub = _closes_from_prices(prices, candidate.ticker)
    closes = [float(v) for v in sub["close"].dropna().tolist()] if not sub.empty and "close" in sub.columns else []
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    beta = None
    if market_closes and len(market_closes) > 20 and len(rets) > 20:
        mrets = [market_closes[i] / market_closes[i - 1] - 1.0 for i in range(1, len(market_closes))]
        n = min(len(rets), len(mrets), 252)
        beta = slope_beta(rets[-n:], mrets[-n:])
    return PRMResult(beta=beta, size_fraction=1.0, blocked=False, block_reason="")


def normalize_earnings_date(raw: object | None) -> str | None:
    """Coerce Yahoo calendars / Python reprs into YYYY-MM-DD."""
    if raw is None:
        return None
    if hasattr(raw, "strftime"):
        try:
            return raw.strftime("%Y-%m-%d")  # type: ignore[union-attr]
        except Exception:
            pass
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    match = re.search(r"datetime\.date\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)", text)
    if match:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return f"{year:04d}-{month:02d}-{day:02d}"
    iso = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if iso:
        return iso.group(1)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def catalyst_window() -> tuple[int, int]:
    """The PTM catalyst window in calendar days (default 30-90).

    The process states 20-60 *trading* days; that is 30-90 calendar days, and the
    earnings buckets use the same units so the two agree.
    """
    raw = (toml_settings().get("filters") or {}).get("catalyst_window_days") or [30, 90]
    return int(raw[0]), int(raw[1])


def earnings_in_window(
    raw_date: str | None,
    low_days: int | None = None,
    high_days: int | None = None,
) -> tuple[bool, str | None]:
    if low_days is None or high_days is None:
        window_low, window_high = catalyst_window()
        low_days = window_low if low_days is None else low_days
        high_days = window_high if high_days is None else high_days
    iso = normalize_earnings_date(raw_date)
    if not iso:
        return False, str(raw_date) if raw_date else None
    # Calendar-date arithmetic, not datetime subtraction: subtracting an
    # end-of-day "now" from a midnight target made a date 30 days out measure 29,
    # so the gate and the earnings buckets could disagree on the same name.
    delta = days_until(iso)
    if delta is None:
        return False, iso
    return low_days <= delta <= high_days, iso
