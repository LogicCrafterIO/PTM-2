import json

import pandas as pd
import pytest

from ptm.asof import set_as_of
from ptm.config import data_dir
from ptm.ingest import expectations as exp
from ptm.io import write_df, write_json


def _seed_prices(ticker="T1"):
    """Two sessions either side of each of three report dates."""
    days = [
        ("2026-01-05", 100.0), ("2026-01-06", 100.0), ("2026-01-07", 90.0),   # -10% on the print
        ("2026-04-05", 90.0), ("2026-04-06", 90.0), ("2026-04-07", 99.0),     # +10%
        ("2026-07-05", 99.0), ("2026-07-06", 99.0), ("2026-07-07", 99.0),     # flat
    ]
    write_df(
        data_dir("curated", "prices.csv"),
        pd.DataFrame(
            [{"date": d, "open": c, "high": c, "low": c, "close": c, "volume": 1, "ticker": ticker}
             for d, c in days]
        ),
    )
    write_json(data_dir("raw", "edgar", f"{ticker}_reportdates.json"),
               ["2026-07-07", "2026-04-07", "2026-01-07"])
    exp._prices.cache_clear()


def test_backdated_run_refuses_every_expectations_source():
    """None of the four can be rolled back to a past vintage, so a backdated run
    must not see any of them — the same rule as consensus estimates."""
    set_as_of("2026-06-15")
    assert exp.expectations("AAPL", "2026-07-01") is None
    assert exp.build_expectations(["AAPL", "MSFT"]) == {}


def test_past_reactions_are_computed_offline():
    _seed_prices()
    out = exp.past_reactions("T1")
    assert out["available"] is True
    # Newest first, matching the EDGAR report-dates file this reads.
    assert [r["report_date"] for r in out["prints"]] == ["2026-07-07", "2026-04-07", "2026-01-07"]
    assert [r["move_pct"] for r in out["prints"]] == [0.0, 10.0, -10.0]
    assert out["avg_abs_move_pct"] == pytest.approx(6.67, abs=0.01)
    assert out["down_prints"] == 1


def test_past_reactions_stop_at_the_run_date():
    """A backdated reaction study must not read prints that had not happened."""
    _seed_prices()
    set_as_of("2026-02-01")
    out = exp.past_reactions("T1")
    assert [r["report_date"] for r in out["prints"]] == ["2026-01-07"]


def test_past_reactions_absent_without_report_dates():
    _seed_prices()
    assert exp.past_reactions("NOSUCH") == {"available": False}


def test_mid_prefers_a_two_sided_market():
    mid, spread = exp._mid({"bid": 9.0, "ask": 11.0, "lastPrice": 50.0})
    assert mid == 10.0 and spread == pytest.approx(20.0)


def test_mid_falls_back_to_last_and_reports_no_spread():
    """A stale last produced a confident 3.4% implied move on a real book name.
    It is still used, but the caller must be able to tell it apart from a quote."""
    mid, spread = exp._mid({"bid": 0.0, "ask": 0.0, "lastPrice": 4.0})
    assert mid == 4.0 and spread is None


def test_summary_lines_flag_a_stale_quote():
    """A real book name showed a confident 3.4% implied move off a last trade
    with no two-sided market behind it. The number is still shown, but it must
    not read as measured."""
    payload = {
        "implied": {"available": True, "implied_move_pct": 3.4, "expiry": "2026-12-18",
                    "quote_basis": "last_trade_only", "thin": False, "open_interest": 3966,
                    "strikes": 25, "two_sided_strikes": 0, "spread_pct": None,
                    "expiry_covers_earnings": True},
    }
    text = " ".join(exp.summary_lines(payload))
    assert "may be stale" in text
    assert "last traded prices" in text


def test_summary_lines_render_each_measure():
    payload = {
        "implied": {"available": True, "implied_move_pct": 31.9, "expiry": "2026-11-20",
                    "quote_basis": "mid", "thin": False, "open_interest": 5000,
                    "spread_pct": 8.0, "expiry_covers_earnings": True},
        "revisions": {"available": True, "change_90d_pct": -12.4, "change_30d_pct": -3.0,
                      "analysts_up_30d": 0, "analysts_down_30d": 5},
        "reactions": {"available": True, "of": 3, "avg_abs_move_pct": 6.7, "down_prints": 2,
                      "prints": [{"move_pct": -10.0}, {"move_pct": 10.0}, {"move_pct": 0.0}]},
        "surprise": {"available": True, "beats": 1, "of": 4, "avg_surprise_pct": -10.6},
    }
    lines = exp.summary_lines(payload)
    blob = " ".join(lines)
    assert "31.9% move" in blob
    assert "-12.4% over 90 days" in blob
    assert "priced" not in blob, "revision momentum is not a mispricing claim"
    assert "0 up, 5 down" in blob
    assert "1 of the last 4 quarters" in blob


def _chain(rows):
    return pd.DataFrame(rows)


def test_liquidity_is_measured_across_the_chain_not_one_strike():
    """The bug this replaces: open interest was read off the single ATM row, so
    a blank row read as an untradeable chain. POWL carries 319 contracts across
    125 strikes with only 28 quotable, and the strike nearest spot is usually
    not one of them — it was flagged thin on a real book, wrongly."""
    calls = _chain([
        {"strike": 100.0, "bid": 0.0, "ask": 0.0, "lastPrice": 6.5, "openInterest": 0, "volume": 2},
        {"strike": 105.0, "bid": 4.0, "ask": 4.4, "lastPrice": 4.2, "openInterest": 150, "volume": 30},
    ])
    liq = exp._chain_liquidity(calls, calls)
    assert liq["open_interest"] == 300, "must sum the chain, not sample one row"
    assert liq["two_sided_strikes"] == 2
    assert liq["strikes"] == 4


def test_straddle_prefers_a_quoted_strike_over_the_exact_atm_one():
    """A mid from a strike 2% away is a real price; lastPrice at the money can
    be days stale."""
    calls = _chain([
        {"strike": 100.0, "bid": 0.0, "ask": 0.0, "lastPrice": 6.5, "openInterest": 0, "volume": 2},
        {"strike": 102.0, "bid": 5.0, "ask": 5.4, "lastPrice": 5.2, "openInterest": 90, "volume": 10},
    ])
    call, put, basis = exp._pick_straddle(calls, calls, 100.0)
    assert basis == "mid"
    assert call["strike"] == 102.0


def test_straddle_will_not_wander_out_of_the_money_for_a_quote():
    """Past ATM_BAND_PCT the straddle stops being at-the-money and the implied
    move it produces is distorted, so a stale last is the better answer."""
    calls = _chain([
        {"strike": 100.0, "bid": 0.0, "ask": 0.0, "lastPrice": 6.5, "openInterest": 0, "volume": 2},
        {"strike": 140.0, "bid": 1.0, "ask": 1.2, "lastPrice": 1.1, "openInterest": 500, "volume": 80},
    ])
    call, put, basis = exp._pick_straddle(calls, calls, 100.0)
    assert basis == "last_trade_only"
    assert call["strike"] == 100.0


def test_thin_flag_now_reflects_the_chain():
    healthy = {"open_interest": 5000, "two_sided_strikes": 30, "strikes": 120}
    dead = {"open_interest": 4, "two_sided_strikes": 0, "strikes": 8}
    assert healthy["open_interest"] >= exp._thin_open_interest()
    assert dead["open_interest"] < exp._thin_open_interest()


def test_summary_reports_quotable_strikes_when_thin():
    payload = {"implied": {"available": True, "implied_move_pct": 12.0, "expiry": "2026-11-20",
                           "quote_basis": "mid", "thin": True, "open_interest": 40,
                           "strikes": 20, "two_sided_strikes": 2, "spread_pct": 30.0,
                           "expiry_covers_earnings": True}}
    blob = " ".join(exp.summary_lines(payload))
    assert "40 contracts of open interest across 20 strikes, 2 of them quotable" in blob


def test_missing_open_interest_reads_as_unknown_not_thin():
    """Found the hard way, twice. Read off one strike this flagged 11 of 12 book
    names; read across the chain it still put ABNB and ANET at zero — two of the
    most liquid option chains in the US market."""
    wide_but_zero = {"open_interest": 0, "strikes": 70, "two_sided_strikes": 0}
    assert exp._open_interest_missing(wide_but_zero) is True
    payload = {"implied": {"available": True, "implied_move_pct": 8.0, "expiry": "2026-11-20",
                           "quote_basis": "last_trade_only", "thin": None,
                           "open_interest_missing": True, "strikes": 70,
                           "expiry_covers_earnings": True}}
    blob = " ".join(exp.summary_lines(payload))
    assert "liquidity UNKNOWN" in blob
    assert "gap in the data rather than an empty market" in blob
    assert "Chain is thin" not in blob


def test_a_narrow_chain_with_no_open_interest_is_believed():
    """A handful of strikes with nothing open is plausibly a real dead chain, so
    that case must stay judgeable rather than being excused as a feed gap."""
    assert exp._open_interest_missing({"open_interest": 0, "strikes": 4}) is False


def test_out_of_hours_fetch_is_labelled():
    payload = {"implied": {"available": True, "implied_move_pct": 8.0, "expiry": "2026-11-20",
                           "quote_basis": "last_trade_only", "thin": False,
                           "open_interest": 500, "strikes": 40, "two_sided_strikes": 0,
                           "expiry_covers_earnings": True}}
    assert "outside market hours" in " ".join(exp.summary_lines(payload))
