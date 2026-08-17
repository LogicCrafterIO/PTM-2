import pandas as pd

from ptm.models import Side
from ptm.quant import build_candidates, classify_long_case, classify_short_case


def test_long_and_short_case_labels():
    assert classify_long_case(0.3, 0.4, 0.1) == "long_case_1_acceleration"
    assert classify_long_case(0.2, 0.2, 0.1) == "long_case_2_stable_above"
    assert classify_long_case(0.3, 0.2, 0.1) == "long_case_3_decel_still_above"
    assert classify_long_case(-0.1, 0.2, 0.1) == "long_case_7_10_turnaround"
    assert classify_long_case(None, 0.1, 0.1) == "unknown"
    assert classify_short_case(-0.2, -0.3, 0.1) == "short_case_1_worsening"
    assert classify_short_case(-0.3, -0.1, 0.1) == "short_case_2_decel_decline"
    assert classify_short_case(0.1, -0.1, 0.1) == "short_case_3_4_xgrowth"
    assert classify_short_case(0.05, 0.04, 0.2) == "short_below_sector"


def test_build_candidates_premium_long_discount_short():
    universe = pd.DataFrame(
        {
            "ticker": ["HI", "MID", "LO"],
            "name": ["Hi", "Mid", "Lo"],
            "sector": ["Industrials"] * 3,
            "industry": ["Machinery"] * 3,
        }
    )
    fundamentals = pd.DataFrame(
        {
            "ticker": ["HI", "MID", "LO"],
            "name": ["Hi", "Mid", "Lo"],
            "sector": ["Industrials"] * 3,
            "industry": ["Machinery"] * 3,
            "price": [100.0, 100.0, 100.0],
            "market_cap": [5e9, 5e9, 30e9],
            "forward_eps": [2.0, 5.0, 20.0],
            "trailing_eps": [1.5, 4.5, 22.0],
            "earnings_growth": [0.2, 0.05, -0.1],
        }
    )
    cands = build_candidates(universe, fundamentals)
    longs = [c for c in cands if c.side == Side.LONG]
    shorts = [c for c in cands if c.side == Side.SHORT]
    assert any(c.ticker == "HI" for c in longs)
    assert any(c.ticker == "LO" for c in shorts)
    assert all(c.pe1 is not None and c.sector_pe1 is not None and c.pe1 >= c.sector_pe1 for c in longs)
    assert all(c.pe1 is not None and c.sector_pe1 is not None and c.pe1 <= c.sector_pe1 for c in shorts)


def test_single_name_sector_is_not_an_outlier():
    universe = pd.DataFrame(
        {"ticker": ["ONLY"], "name": ["Only"], "sector": ["Utilities"], "industry": ["Multi-Utilities"]}
    )
    fundamentals = pd.DataFrame(
        {
            "ticker": ["ONLY"],
            "name": ["Only"],
            "sector": ["Utilities"],
            "industry": ["Multi-Utilities"],
            "price": [100.0],
            "market_cap": [30e9],
            "forward_eps": [5.0],
            "trailing_eps": [4.8],
            "earnings_growth": [0.05],
        }
    )
    cands = build_candidates(universe, fundamentals)
    assert cands == []
