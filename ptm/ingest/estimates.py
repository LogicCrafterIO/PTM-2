"""Analyst consensus EPS estimates.

This is the one input EDGAR structurally cannot supply. EDGAR holds what
companies *filed*; consensus is what analysts *expect*, and it is a proprietary
product that never appears in a filing. The PTM screen is built on forward
multiples and forward growth, so an EDGAR-only design cannot express it — the
two requirements are in genuine tension, and this module is where that tension
is resolved explicitly rather than silently.

What it changes: `eps1` and `eps2` become two **independent** estimates, so
`eg1` and `eg2` are independent growth rates and the EG taxonomy works. Derived
from realised growth they were the same number, and the cases that compare them
were decided by floating-point noise (see docs/EG-CASES.md).

Two boundaries matter:

* **Basis.** Consensus EPS is normally adjusted/non-GAAP. Growth is therefore
  computed against `yearAgoEps` from the *same* table, never against EDGAR's
  GAAP trailing EPS. Mixing the two produces a meaningless ratio. Trailing P/E
  stays on EDGAR GAAP and remains exact.
* **Vintage.** These are today's estimates with no history. A backdated run must
  not touch them — that would be lookahead of exactly the kind the rest of the
  pipeline works to prevent. `consensus_eps` refuses to serve a backdated run.
"""

from __future__ import annotations

import time

from ptm.asof import is_backdated
from ptm.config import data_dir, toml_settings
from ptm.io import read_json, write_json
from ptm.log import log

PERIOD_CURRENT = "0y"
PERIOD_NEXT = "+1y"


def _cfg() -> dict:
    return toml_settings().get("estimates") or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def min_analysts() -> int:
    return int(_cfg().get("min_analysts") or 2)


def _max_age_days() -> int:
    return int(_cfg().get("max_age_days") or 2)


def _cache_fresh(path) -> bool:
    if not path.exists():
        return False
    max_age = _max_age_days()
    if max_age <= 0:
        return True
    return (time.time() - path.stat().st_mtime) / 86400.0 <= max_age


def _cell(frame, period: str, column: str) -> float | None:
    try:
        value = frame.loc[period, column]
    except Exception:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # drop NaN


def consensus_eps(ticker: str) -> dict | None:
    """Consensus EPS for the current and next fiscal year.

    Returns None when unavailable, too thinly covered, disabled, or when the run
    is backdated (these estimates carry no history, so using them then would be
    lookahead).
    """
    if not enabled() or is_backdated():
        return None
    cache = data_dir("raw", "estimates", f"{ticker}.json")
    if _cache_fresh(cache):
        try:
            cached = read_json(cache)
            if isinstance(cached, dict):
                return cached or None
        except Exception:
            pass

    import yfinance as yf

    try:
        frame = yf.Ticker(ticker).earnings_estimate
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None

    eps1 = _cell(frame, PERIOD_CURRENT, "avg")
    eps2 = _cell(frame, PERIOD_NEXT, "avg")
    prior = _cell(frame, PERIOD_CURRENT, "yearAgoEps")
    analysts = _cell(frame, PERIOD_CURRENT, "numberOfAnalysts") or 0
    # Yahoo's own growth column, on the same basis as the estimates.
    eg1 = _cell(frame, PERIOD_CURRENT, "growth")
    eg2 = _cell(frame, PERIOD_NEXT, "growth")

    if eps1 is None or eps2 is None:
        write_json(cache, {})
        return None
    if analysts < min_analysts():
        # A two-analyst "consensus" is one opinion with a rounding error.
        write_json(cache, {})
        return None

    # Prefer deriving growth ourselves so it always matches the EPS we screen on.
    if prior not in (None, 0) and prior > 0:
        eg1 = eps1 / prior - 1.0
    if eps1 not in (None, 0) and eps1 > 0:
        eg2 = eps2 / eps1 - 1.0

    payload = {
        "ticker": ticker,
        "eps1": eps1,
        "eps2": eps2,
        "prior_eps": prior,
        "eg1": eg1,
        "eg2": eg2,
        "analysts": int(analysts),
        "basis": "analyst consensus (adjusted basis; growth measured against the "
        "same table's yearAgoEps, never against GAAP trailing EPS)",
    }
    write_json(cache, payload)
    return payload


def warn_if_thin(rows: int, with_consensus: int) -> list[str]:
    """Coverage caveat for the run summary."""
    if not enabled():
        return ["Analyst consensus disabled; forward EPS is extrapolated realised growth."]
    if is_backdated():
        return [
            "BACKDATED RUN: analyst consensus withheld (today's estimates have no "
            "history, so using them would be lookahead). Forward EPS is extrapolated "
            "realised growth, and the EG cases that compare eg2 to eg1 are not reachable."
        ]
    if rows and with_consensus < 0.8 * rows:
        return [
            f"Analyst consensus covered only {with_consensus}/{rows} names; the rest "
            "fall back to extrapolated realised growth, where eg2 equals eg1."
        ]
    return []


def log_coverage(rows: int, with_consensus: int) -> None:
    if not rows:
        return
    log(f"estimates: consensus on {with_consensus}/{rows} names ({with_consensus / rows:.0%})")
