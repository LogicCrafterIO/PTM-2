from datetime import date

import pandas as pd

from ptm.models import Candidate, Side
from ptm.risk import earnings_in_window, normalize_earnings_date, prm_for
from tests.conftest import make_price_history


def _prices(ticker: str, drift: float) -> pd.DataFrame:
    return make_price_history(ticker, start=100.0, drift=drift, days=80)


def test_no_technical_analysis_surface_remains():
    """Timing lights were removed from the process; nothing should reintroduce them."""
    import ptm.formulas as formulas
    import ptm.risk as timing
    from ptm.models import TimingResult

    for name in ("time_idea", "sma", "ema"):
        assert not hasattr(timing, name), f"{name} is technical analysis and must stay out"
        assert not hasattr(formulas, name), f"{name} is technical analysis and must stay out"
    assert set(TimingResult.model_fields) == {"comment"}


def test_normalize_and_earnings_window():
    assert normalize_earnings_date("[datetime.date(2026, 7, 31)]") == "2026-07-31"
    assert normalize_earnings_date(date(2026, 10, 1)) == "2026-10-01"
    assert normalize_earnings_date("2026-09-20 00:00:00") == "2026-09-20"
    assert normalize_earnings_date(None) is None
    in_window, parsed = earnings_in_window("[datetime.date(2026, 9, 20)]")
    assert parsed == "2026-09-20"
    assert in_window is True
    empty, missing = earnings_in_window(None)
    assert empty is False and missing is None


def test_prm_carries_beta_only():
    """stop_pct/target_pct/r_score/atrp were removed with the move to options.
    beta stays: ptm/book.py swaps names on it to hold the book inside its limit."""
    prices = make_price_history("Q1", start=100.0, drift=0.2, days=80)
    result = prm_for(prices, Candidate(ticker="Q1", side=Side.LONG))
    assert set(type(result).model_fields) == {"beta", "size_fraction", "blocked", "block_reason"}
    assert result.blocked is False


def test_beta_measures_against_the_index():
    """A name that moves twice the index should read near 2, not near 1."""
    prices = make_price_history("B1", start=100.0, drift=0.2, days=80)
    closes = [float(c) for c in prices["close"].tolist()]
    # Market series whose daily returns are exactly half the stock's.
    market = [100.0]
    for i in range(1, len(closes)):
        market.append(market[-1] * (1 + (closes[i] / closes[i - 1] - 1.0) / 2))
    result = prm_for(prices, Candidate(ticker="B1", side=Side.LONG), market_closes=market)
    assert result.beta is not None
    assert abs(result.beta - 2.0) < 0.05, result.beta


def test_beta_is_none_without_enough_history():
    """A guess would silently become 1.0 in the book; None is honest."""
    prices = make_price_history("S1", start=100.0, drift=0.2, days=80)
    assert prm_for(prices, Candidate(ticker="S1", side=Side.LONG)).beta is None
    assert prm_for(prices, Candidate(ticker="S1", side=Side.LONG), market_closes=[100.0, 101.0]).beta is None


def test_window_boundaries_are_exact_calendar_days():
    """The gate and the buckets must agree on the same name, so the window is
    measured in whole calendar days rather than datetime deltas."""
    from datetime import timedelta

    from ptm.asof import as_of_date
    from ptm.organize import bucket_for_days
    from ptm.risk import catalyst_window, earnings_in_window

    low, high = catalyst_window()
    today = as_of_date()
    for offset, expected in ((low - 1, False), (low, True), (high, True), (high + 1, False)):
        iso = (today + timedelta(days=offset)).isoformat()
        in_window, parsed = earnings_in_window(iso)
        assert in_window is expected, f"{offset}d should be in_window={expected}"
        assert parsed == iso
    # And the bucket for the top of the window is the last primary bucket.
    assert bucket_for_days(high) == "61-90d"
