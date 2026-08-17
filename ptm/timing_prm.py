from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

import re

from ptm.config import toml_settings
from ptm.formulas import atrp, ema, high_to_low, r_score, slope_beta, sma, true_range_pct
from ptm.models import Candidate, PRMResult, Side, TimingLight, TimingResult


def _closes_from_prices(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    sub = prices[prices["ticker"] == ticker].copy()
    if sub.empty:
        return sub
    sub.columns = [str(c).lower() for c in sub.columns]
    date_col = "date" if "date" in sub.columns else "datetime"
    if date_col in sub.columns:
        sub = sub.sort_values(date_col)
    return sub


def time_idea(prices: pd.DataFrame, ticker: str, side: Side | None = None) -> TimingResult:
    sub = _closes_from_prices(prices, ticker)
    if sub.empty or "close" not in sub.columns:
        return TimingResult(light=TimingLight.UNKNOWN, comment="no price history")
    closes = [float(v) for v in sub["close"].dropna().tolist()]
    s20, s60 = sma(closes, 20), sma(closes, 60)
    e20, e60 = ema(closes, 20), ema(closes, 60)
    macd = None if e20 is None or e60 is None else e20 - e60
    light = TimingLight.UNKNOWN
    if s20 is not None and s60 is not None:
        uptrend = s20 > s60 and (macd or 0) > 0
        downtrend = s20 < s60 and (macd or 0) < 0
        if side == Side.SHORT:
            if downtrend:
                light = TimingLight.GREEN
            elif uptrend:
                light = TimingLight.RED
            else:
                light = TimingLight.AMBER
        elif uptrend:
            light = TimingLight.GREEN
        elif downtrend:
            light = TimingLight.RED
        else:
            light = TimingLight.AMBER
    return TimingResult(
        light=light,
        sma20=s20,
        sma60=s60,
        ema20=e20,
        ema60=e60,
        macd=macd,
        comment=f"20/60 SMA {light.value}; MACD {macd:.4f}" if macd is not None else light.value,
    )


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
    blocked = score is not None and score < cfg["min_r_score"]
    return PRMResult(
        stop_pct=stop,
        target_pct=target,
        r_score=score,
        atrp=atr,
        beta=beta,
        size_fraction=1.0,
        blocked=blocked,
        block_reason="R-score below minimum" if blocked else "",
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


def earnings_in_window(raw_date: str | None, low_days: int = 20, high_days: int = 60) -> tuple[bool, str | None]:
    iso = normalize_earnings_date(raw_date)
    if not iso:
        return False, str(raw_date) if raw_date else None
    parsed = datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    delta = (parsed - datetime.now(timezone.utc)).days
    return low_days <= delta <= high_days, iso
