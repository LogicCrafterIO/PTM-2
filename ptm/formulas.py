"""Course formulas: EG, PEG, EV, ATRP, DoR, SMA/EMA, beta."""

from __future__ import annotations

import math


def earnings_growth(eps_now: float | None, eps_prev: float | None) -> float | None:
    if eps_now is None or eps_prev is None:
        return None
    if eps_prev == 0 and eps_now == 0:
        return 0.0
    if eps_prev > 0 and eps_now < 0:
        return -1.0
    if eps_prev < 0 and eps_now > 0:
        return 1.0
    if eps_prev == 0:
        return 1.0 if eps_now > 0 else -1.0
    return (eps_now - eps_prev) / abs(eps_prev)


def pe(price: float | None, eps: float | None) -> float | None:
    if price is None or eps is None or eps <= 0:
        return None
    return price / eps


def peg(pe_value: float | None, eg: float | None) -> float | None:
    if pe_value is None or eg is None or eg <= 0:
        return None
    return pe_value / (eg * 100.0)


def enterprise_value(market_cap: float | None, debt: float | None, cash: float | None) -> float | None:
    if market_cap is None:
        return None
    return market_cap + (debt or 0.0) - (cash or 0.0)


def ev_multiple(ev: float | None, operating: float | None) -> float | None:
    if ev is None or operating is None or operating <= 0:
        return None
    return ev / operating


def bear_level(index_high: float, drawdown: float = 0.20) -> float:
    return index_high * (1.0 - drawdown)


def true_range_pct(high: float, low: float, prev_close: float, open_: float) -> float | None:
    if open_ == 0:
        return None
    tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
    return tr / open_


def atrp(true_range_pcts: list[float]) -> float | None:
    if not true_range_pcts:
        return None
    return sum(true_range_pcts) / len(true_range_pcts)


def close_to_close(prev_close: float, close: float) -> float | None:
    if prev_close == 0:
        return None
    return close / prev_close - 1.0


def high_to_low(high: float, low: float) -> float | None:
    if low == 0:
        return None
    return high / low - 1.0


def r_score(target_pct: float | None, stop_pct: float | None) -> float | None:
    if target_pct is None or stop_pct is None or stop_pct <= 0:
        return None
    return target_pct / stop_pct


def slope_beta(y: list[float], x: list[float]) -> float | None:
    n = min(len(y), len(x))
    if n < 10:
        return None
    y = y[-n:]
    x = x[-n:]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den = sum((xi - mean_x) ** 2 for xi in x)
    if den == 0:
        return None
    return num / den


def annualized_vol(returns: list[float], periods_per_year: int = 252) -> float | None:
    n = len(returns)
    if n < 5:
        return None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(var) * math.sqrt(periods_per_year)
