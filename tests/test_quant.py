import pandas as pd
import pytest

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


def _frame(rows):
    import pandas as pd

    universe = pd.DataFrame(
        [{"ticker": r["ticker"], "name": r["ticker"], "sector": r["sector"], "industry": "X"} for r in rows]
    )
    fundamentals = pd.DataFrame(
        [
            {
                "ticker": r["ticker"],
                "price": r["price"],
                "forward_eps": r["forward_eps"],
                "trailing_eps": r.get("trailing_eps", r["forward_eps"]),
                "earnings_growth": r.get("growth", 0.05),
                "market_cap": r.get("market_cap", 5_000_000_000),
            }
            for r in rows
        ]
    )
    return universe, fundamentals


def test_sector_benchmark_is_the_median_not_the_mean():
    """One near-zero-EPS name must not drag the whole sector benchmark up."""
    from ptm.config import data_dir
    from ptm.io import read_df

    rows = [
        {"ticker": "A1", "sector": "Industrials", "price": 100.0, "forward_eps": 10.0},   # PE 10
        {"ticker": "A2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0},    # PE 20
        {"ticker": "A3", "sector": "Industrials", "price": 100.0, "forward_eps": 3.3333}, # PE 30
        {"ticker": "A4", "sector": "Industrials", "price": 100.0, "forward_eps": 1.0},    # PE 100
    ]
    build_candidates(*_frame(rows))
    table = read_df(data_dir("curated", "quant_table.csv"))
    median = float(table["sector_pe1"].dropna().iloc[0])
    mean = float(table["sector_pe1_mean"].dropna().iloc[0])
    assert median == pytest.approx(25.0, rel=1e-3)   # (20 + 30) / 2
    assert mean == pytest.approx(40.0, rel=1e-2)     # dragged up by the PE-100 name
    assert median < mean


def test_implausible_pe_is_excluded_from_screen_and_benchmark():
    from ptm.config import data_dir
    from ptm.io import read_df

    rows = [
        {"ticker": "B1", "sector": "Industrials", "price": 100.0, "forward_eps": 10.0},
        {"ticker": "B2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0},
        {"ticker": "B3", "sector": "Industrials", "price": 100.0, "forward_eps": 4.0},
        # EPS of 0.08 -> P/E 1250: a rounding artefact, not a valuation.
        {"ticker": "JUNK", "sector": "Industrials", "price": 100.0, "forward_eps": 0.08},
    ]
    candidates = build_candidates(*_frame(rows))
    table = read_df(data_dir("curated", "quant_table.csv"))
    junk = table[table["ticker"] == "JUNK"].iloc[0]
    assert bool(junk["pe_implausible"]) is True
    assert "JUNK" not in {c.ticker for c in candidates}
    # And it must not have moved the benchmark either.
    assert float(table["sector_pe1"].dropna().iloc[0]) <= 25.0


def test_loss_makers_do_not_lift_the_sector_growth_benchmark():
    """A shrinking loss reads as +50% growth; such names must stay out of the
    benchmark, since they can never be screened themselves (no positive P/E)."""
    from ptm.config import data_dir
    from ptm.io import read_df

    rows = [
        {"ticker": "C1", "sector": "Industrials", "price": 100.0, "forward_eps": 10.0, "trailing_eps": 9.5},
        {"ticker": "C2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "trailing_eps": 4.8},
        # Loss-maker: EPS -2.00 -> -1.00 registers as strong positive growth.
        {"ticker": "LOSS", "sector": "Industrials", "price": 100.0, "forward_eps": -1.0, "trailing_eps": -2.0},
    ]
    candidates = build_candidates(*_frame(rows))
    table = read_df(data_dir("curated", "quant_table.csv"))
    loss = table[table["ticker"] == "LOSS"].iloc[0]
    assert pd.isna(loss["pe1"])                      # no positive P/E, so unscreenable
    assert "LOSS" not in {c.ticker for c in candidates}
    benchmark = float(table["sector_eg1"].dropna().iloc[0])
    loss_eg1 = float(loss["eg1"])
    assert loss_eg1 > 0                               # the shrinking loss does look like growth
    assert benchmark < loss_eg1                       # but it is not in the benchmark


def test_candidates_must_fit_a_process_eg_case():
    """Selecting on P/E extremity alone surfaced names at 3-12x their sector
    multiple that fit no long/short case, and the qualitative pass rejected
    100% of them. A candidate must fit a case."""
    from ptm.quant import NON_IDEAL_CASES

    rows = []
    # Six names with a clean accelerating-growth long case.
    for i in range(6):
        rows.append({
            "ticker": f"OK{i}", "sector": "Industrials", "price": 100.0,
            "forward_eps": 4.0 - i * 0.1, "trailing_eps": 3.0 - i * 0.1, "growth": 0.30,
        })
    # An extreme multiple whose earnings are going backwards: no valid case.
    rows.append({
        "ticker": "EXPENSIVE", "sector": "Industrials", "price": 100.0,
        "forward_eps": 0.9, "trailing_eps": 3.0, "growth": -0.40,
    })
    candidates = build_candidates(*_frame(rows))
    picked = {c.ticker for c in candidates}
    # It has by far the highest P/E, so P/E-extremity alone would select it.
    assert "EXPENSIVE" not in picked
    for cand in candidates:
        assert cand.eg_case not in NON_IDEAL_CASES


def test_require_eg_case_can_be_switched_off(monkeypatch):
    """The old behaviour stays reachable, since it is a process decision."""
    import ptm.quant as quant
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "filters": {**base["filters"], "require_eg_case": False}}
    monkeypatch.setattr(quant, "toml_settings", lambda: patched)

    rows = [
        {"ticker": f"N{i}", "sector": "Industrials", "price": 100.0,
         "forward_eps": 4.0 - i * 0.1, "trailing_eps": 3.0 - i * 0.1, "growth": 0.30}
        for i in range(6)
    ]
    rows.append({"ticker": "EXPENSIVE", "sector": "Industrials", "price": 100.0,
                 "forward_eps": 0.9, "trailing_eps": 3.0, "growth": -0.40})
    picked = {c.ticker for c in build_candidates(*_frame(rows))}
    assert "EXPENSIVE" in picked
