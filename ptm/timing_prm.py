"""Position risk maths (ATR stop, range target, beta).

No entry timing lives here. The SMA/EMA/MACD timing lights this module used to
compute were removed: technical analysis takes no part in screening. What
remains is risk sizing applied *after* a name is selected, and it gates nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

import re

from ptm.asof import days_until
from ptm.config import toml_settings
from ptm.formulas import atrp, high_to_low, r_score, slope_beta, true_range_pct
from ptm.models import Candidate, PRMResult, Side


def _closes_from_prices(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    sub = prices[prices["ticker"] == ticker].copy()
    if sub.empty:
        return sub
    sub.columns = [str(c).lower() for c in sub.columns]
    date_col = "date" if "date" in sub.columns else "datetime"
    if date_col in sub.columns:
        sub = sub.sort_values(date_col)
    return sub


def _true_ranges(sub: pd.DataFrame) -> list[float]:
    trs: list[float] = []
    if sub.empty or not {"high", "low", "close", "open"}.issubset(sub.columns):
        return trs
    prev = None
    for _, row in sub.iterrows():
        if prev is not None:
            tr = true_range_pct(float(row["high"]), float(row["low"]), prev, float(row["open"]))
            if tr is not None:
                trs.append(tr)
        prev = float(row["close"])
    return trs


def _range_pct(sub: pd.DataFrame, lookback: int) -> float | None:
    """Independent target: high-low range over lookback days / last close."""
    if sub.empty or not {"high", "low", "close"}.issubset(sub.columns):
        return None
    window = sub.tail(lookback)
    if len(window) < max(20, lookback // 2):
        return None
    high = float(window["high"].max())
    low = float(window["low"].min())
    close = float(window["close"].iloc[-1])
    return high_to_low(high, low) if close else None


def prm_for(prices: pd.DataFrame, candidate: Candidate, market_closes: list[float] | None = None) -> PRMResult:
    cfg = toml_settings()["prm"]
    sub = _closes_from_prices(prices, candidate.ticker)
    trs = _true_ranges(sub)
    lookback = int(cfg["atrp_stop_lookback"])
    atr = atrp(trs[-lookback:]) if trs else None
    stop = atr if atr is not None else 0.08
    target_lookback = int(cfg.get("atrp_target_lookback") or 63)
    target = _range_pct(sub, target_lookback)
    if target is None:
        target = stop * float(cfg["atrp_target_multiple"])
    score = r_score(target, stop)
    closes = [float(v) for v in sub["close"].dropna().tolist()] if not sub.empty and "close" in sub.columns else []
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    beta = None
    if market_closes and len(market_closes) > 20 and len(rets) > 20:
        mrets = [market_closes[i] / market_closes[i - 1] - 1.0 for i in range(1, len(market_closes))]
        n = min(len(rets), len(mrets), 252)
        beta = slope_beta(rets[-n:], mrets[-n:])
    return PRMResult(
        stop_pct=stop,
        target_pct=target,
        r_score=score,
        atrp=atr,
        beta=beta,
        size_fraction=1.0,
        blocked=False,
        block_reason="",
    )


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
