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
            "forward_source": ["analyst_consensus"] * 3,
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
                # These tests are about the screen, not the estimate source, so
                # default to consensus; the exclusion has its own test.
                "forward_source": r.get("source", "analyst_consensus"),
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
    patched = {
        **base,
        "filters": {**base["filters"], "require_eg_case": False, "max_relative_peg": 0},
    }
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


def test_eg_cases_do_not_split_on_floating_point_noise():
    """Without a real second-year estimate eg2 is derived from eg1 and the two
    are equal to ~1e-16. Comparing them raw labelled 19 names 'acceleration' and
    8 'worsening' on rounding alone."""
    g = 0.21052631578947342
    noise_up = 0.21052631578947376     # same number, different float path
    noise_down = 0.21052631578947300

    assert classify_long_case(g, noise_up, 0.05) == "long_case_2_stable_above"
    assert classify_long_case(g, noise_down, 0.05) == "long_case_2_stable_above"
    # A real acceleration still registers.
    assert classify_long_case(0.20, 0.30, 0.05) == "long_case_1_acceleration"
    assert classify_long_case(0.30, 0.20, 0.05) == "long_case_3_decel_still_above"

    assert classify_short_case(-0.21, -0.21 + 1e-15, 0.05) != "short_case_2_decel_decline"
    assert classify_short_case(-0.21, -0.21 - 1e-15, 0.05) != "short_case_1_worsening"
    # Real divergence still registers.
    assert classify_short_case(-0.10, -0.30, 0.05) == "short_case_1_worsening"
    assert classify_short_case(-0.30, -0.10, 0.05) == "short_case_2_decel_decline"


def _frame_with_source(rows):
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
                "earnings_growth": r.get("growth", 0.10),
                "market_cap": 5_000_000_000,
                "forward_source": r.get("source", "analyst_consensus"),
                "eg1": r.get("eg1"),
                "eg2": r.get("eg2"),
                "forward_eps2": r.get("forward_eps2"),
            }
            for r in rows
        ]
    )
    return universe, fundamentals


def test_names_without_consensus_are_excluded_from_screen_and_benchmark():
    """Consensus EPS is adjusted and ~18% above GAAP trailing, so a fallback
    name's P/E uses a smaller denominator. Keeping it both misprices that name
    and drags the sector median every other name is judged against."""
    from ptm.config import data_dir
    from ptm.io import read_df

    rows = [
        {"ticker": "C1", "sector": "Industrials", "price": 100.0, "forward_eps": 10.0, "eg1": 0.20, "eg2": 0.10},
        {"ticker": "C2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "eg1": 0.18, "eg2": 0.09},
        {"ticker": "C3", "sector": "Industrials", "price": 100.0, "forward_eps": 4.0, "eg1": 0.15, "eg2": 0.08},
        # No consensus: GAAP-basis EPS, so an inflated P/E on a different basis.
        {"ticker": "NOEST", "sector": "Industrials", "price": 100.0, "forward_eps": 1.0,
         "source": "extrapolated", "eg1": 0.5, "eg2": 0.5},
    ]
    candidates = build_candidates(*_frame_with_source(rows))
    assert "NOEST" not in {c.ticker for c in candidates}

    table = read_df(data_dir("curated", "quant_table.csv"))
    assert bool(table.loc[table["ticker"] == "NOEST", "no_consensus"].iloc[0]) is True
    # And it must not have moved the benchmark: median of 10, 20, 25 -> 20.
    assert float(table["sector_pe1"].dropna().iloc[0]) == pytest.approx(20.0)


def test_backdated_runs_do_not_require_consensus(monkeypatch):
    """Consensus is refused when backdating, so requiring it would empty the screen."""
    from ptm.asof import set_as_of

    rows = [
        {"ticker": f"B{i}", "sector": "Industrials", "price": 100.0,
         "forward_eps": 10.0 - i, "trailing_eps": 8.0 - i, "growth": 0.25,
         "source": "extrapolated"}
        for i in range(4)
    ]
    set_as_of("2026-07-20")
    try:
        candidates = build_candidates(*_frame_with_source(rows))
    finally:
        set_as_of(None)
    assert candidates, "a backdated screen must still produce candidates"


def test_relative_pe_ceiling_blocks_indefensible_longs(monkeypatch):
    """max_screen_pe catches a near-zero EPS; this catches a real but
    indefensible valuation. RXO reached the book at 8.7x its sector median."""
    from ptm.config import data_dir
    from ptm.io import read_df

    rows = [
        {"ticker": "A1", "sector": "Industrials", "price": 100.0, "forward_eps": 10.0, "eg1": 0.30, "eg2": 0.20},
        {"ticker": "A2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "eg1": 0.28, "eg2": 0.19},
        {"ticker": "A3", "sector": "Industrials", "price": 100.0, "forward_eps": 4.0, "eg1": 0.26, "eg2": 0.18},
        # P/E 500 against a ~20 median: real earnings, indefensible multiple.
        {"ticker": "RICH", "sector": "Industrials", "price": 100.0, "forward_eps": 0.2, "eg1": 0.40, "eg2": 0.35},
    ]
    candidates = build_candidates(*_frame_with_source(rows))
    assert "RICH" not in {c.ticker for c in candidates}

    # But it stays in the benchmark: the valuation is real, it is just not a trade.
    table = read_df(data_dir("curated", "quant_table.csv"))
    rich = table[table["ticker"] == "RICH"].iloc[0]
    assert bool(rich["no_consensus"]) is False
    assert float(rich["pe1"]) == pytest.approx(500.0)


def test_relative_ceiling_can_be_disabled(monkeypatch):
    import ptm.quant as quant
    from ptm.config import toml_settings

    base = toml_settings()
    # Both relative ceilings off: this test is about max_sector_pe_multiple, and
    # max_relative_peg would otherwise catch RICH on its own.
    patched = {**base, "filters": {**base["filters"], "max_sector_pe_multiple": 0, "max_relative_peg": 0}}
    monkeypatch.setattr(quant, "toml_settings", lambda: patched)
    rows = [
        {"ticker": "A1", "sector": "Industrials", "price": 100.0, "forward_eps": 10.0, "eg1": 0.30, "eg2": 0.20},
        {"ticker": "A2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "eg1": 0.28, "eg2": 0.19},
        {"ticker": "A3", "sector": "Industrials", "price": 100.0, "forward_eps": 4.0, "eg1": 0.26, "eg2": 0.18},
        {"ticker": "RICH", "sector": "Industrials", "price": 100.0, "forward_eps": 0.6, "eg1": 0.40, "eg2": 0.35},
    ]
    assert "RICH" in {c.ticker for c in build_candidates(*_frame_with_source(rows))}


def _peg_rows():
    """One sector where the premium names differ only in whether growth backs them."""
    return [
        {"ticker": "BASE1", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "eg1": 0.10, "eg2": 0.10},
        {"ticker": "BASE2", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "eg1": 0.10, "eg2": 0.10},
        {"ticker": "BASE3", "sector": "Industrials", "price": 100.0, "forward_eps": 5.0, "eg1": 0.10, "eg2": 0.10},
        # 2.5x the sector multiple bought with 2.3x the sector growth -> relPEG 1.10.
        {"ticker": "EARNED", "sector": "Industrials", "price": 100.0, "forward_eps": 2.0, "eg1": 1.50, "eg2": 0.60},
        # 4.2x the sector multiple on sector-average growth -> relPEG 4.17.
        # Note this still sits under max_sector_pe_multiple = 5.0, so the flat
        # ceiling would wave it through and only the growth-relative one stops it.
        {"ticker": "UNEARNED", "sector": "Industrials", "price": 100.0, "forward_eps": 1.2, "eg1": 0.10, "eg2": 0.10},
    ]


def test_relative_peg_admits_premium_that_growth_backs(monkeypatch):
    """The distinction a flat P/E ceiling cannot draw: both names pay the same
    multiple premium, only one is buying growth with it."""
    import ptm.quant as quant
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "filters": {**base["filters"], "max_relative_peg": 3.0, "require_eg_case": False}}
    monkeypatch.setattr(quant, "toml_settings", lambda: patched)
    picked = {c.ticker for c in build_candidates(*_frame_with_source(_peg_rows())) if c.side == Side.LONG}
    assert "EARNED" in picked
    assert "UNEARNED" not in picked


def test_relative_peg_ceiling_can_be_disabled(monkeypatch):
    import ptm.quant as quant
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {
        **base,
        "filters": {**base["filters"], "max_relative_peg": 0, "max_sector_pe_multiple": 0, "require_eg_case": False},
    }
    monkeypatch.setattr(quant, "toml_settings", lambda: patched)
    picked = {c.ticker for c in build_candidates(*_frame_with_source(_peg_rows())) if c.side == Side.LONG}
    assert "UNEARNED" in picked


def test_relative_peg_is_recorded_on_every_candidate(monkeypatch):
    """Visible whether or not it binds, so the number can be checked."""
    import ptm.quant as quant
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "filters": {**base["filters"], "max_relative_peg": 0, "require_eg_case": False}}
    monkeypatch.setattr(quant, "toml_settings", lambda: patched)
    cands = build_candidates(*_frame_with_source(_peg_rows()))
    unearned = next(c for c in cands if c.ticker == "UNEARNED")
    assert unearned.relative_peg is not None and unearned.relative_peg > 2.0
