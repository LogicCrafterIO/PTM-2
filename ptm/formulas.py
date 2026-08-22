"""Course formulas: EG, PEG, relative PEG, EV, beta."""

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


def relative_peg(
    pe1: float | None,
    sector_pe1: float | None,
    eg1: float | None,
    sector_eg1: float | None,
) -> float | None:
    """How much multiple premium a name charges per unit of growth premium.

    A flat ceiling on pe1/sector_pe1 cannot tell a premium that growth backs
    from one it does not, and the process buys premium-multiple longs on
    purpose, so a flat rule either admits everything or rejects the strategy.
    This divides the two premiums:

        (pe1 / sector_pe1) / ((1 + eg1) / (1 + sector_eg1))

    Below 1.0 the extra growth more than covers the extra multiple. Measured on
    one run's book it ordered the longs the way two independent human reviewers
    did: SEZL 1.39, RSI 1.55, POWL 1.85, BROS 2.53, CWST 3.80, CRK 3.97.

    Returns None when it cannot be formed rather than guessing - a name whose
    earnings have gone to zero has no meaningful growth premium, and the EG-case
    taxonomy is what excludes those.
    """
    if pe1 is None or not sector_pe1 or eg1 is None or sector_eg1 is None:
        return None
    growth_premium = 1.0 + sector_eg1
    if growth_premium == 0:
        return None
    growth_premium = (1.0 + eg1) / growth_premium
    if growth_premium <= 0:
        return None
    return (pe1 / sector_pe1) / growth_premium


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
