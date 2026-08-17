from datetime import date

import pandas as pd

from ptm.models import Candidate, Side, TimingLight
from ptm.timing_prm import earnings_in_window, normalize_earnings_date, prm_for, time_idea
from tests.conftest import make_price_history


def _prices(ticker: str, drift: float) -> pd.DataFrame:
    return make_price_history(ticker, start=100.0, drift=drift, days=80)


def test_long_uptrend_is_green():
    prices = _prices("L1", drift=8.0)
    result = time_idea(prices, "L1", Side.LONG)
    assert result.light == TimingLight.GREEN
    assert result.sma20 is not None and result.sma60 is not None
    assert result.sma20 > result.sma60


def test_short_uptrend_is_red():
    prices = _prices("S1", drift=8.0)
    result = time_idea(prices, "S1", Side.SHORT)
    assert result.light == TimingLight.RED


def test_short_downtrend_is_green():
    prices = _prices("S2", drift=-8.0)
    result = time_idea(prices, "S2", Side.SHORT)
    assert result.light == TimingLight.GREEN


def test_missing_prices_unknown():
    prices = pd.DataFrame(columns=["date", "open", "high", "low", "close", "ticker"])
    result = time_idea(prices, "ZZZ", Side.LONG)
    assert result.light == TimingLight.UNKNOWN


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


def test_r_score_is_not_a_constant_multiple():
    quiet = make_price_history("Q1", start=100.0, drift=0.2, days=80)
    trend = make_price_history("T1", start=100.0, drift=12.0, days=80)
    quiet_prm = prm_for(quiet, Candidate(ticker="Q1", side=Side.LONG))
    trend_prm = prm_for(trend, Candidate(ticker="T1", side=Side.LONG))
    assert quiet_prm.r_score is not None and trend_prm.r_score is not None
    assert abs(quiet_prm.r_score - 3.0) > 0.05
    assert abs(quiet_prm.r_score - trend_prm.r_score) > 0.05
    assert quiet_prm.blocked is False
    assert trend_prm.blocked is False
