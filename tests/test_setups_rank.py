"""Tests for ptm_setups: the group-only fundamental ranking.

Three properties carry the design and each gets a test that fails loudly if it
regresses: the packets contain no price data of any kind, the factual table
columns are computed rather than taken from the model's prose, and the
"this side opposes the name's own revisions" flag is derived here instead of
trusted from the model.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

REF = date(2026, 9, 2)


# ---------------------------------------------------------------- fixtures

def _exp_payload(ticker: str, *, rev90: float | None, rev30: float | None = None,
                 up: int | None = 5, down: int | None = 1,
                 surprise: list[tuple[str, float, float, float]] | None = None,
                 earnings_date: str | None = "2026-11-05") -> dict:
    """An expectations cache the way ptm.ingest.expectations writes it —
    including the `reactions` block, which the ranking must never read."""
    prints = [
        {"quarter": q, "actual": a, "estimate": e, "surprise_pct": s}
        for q, a, e, s in (surprise or [])
    ]
    return {
        "ticker": ticker,
        "as_of": "2026-08-30T13:57:55+00:00",
        "earnings_date": earnings_date,
        "revisions": {
            "available": rev90 is not None,
            "change_90d_pct": rev90,
            "change_30d_pct": rev30,
            "analysts_up_30d": up,
            "analysts_down_30d": down,
        },
        "surprise": {
            "available": bool(prints),
            "prints": prints,
            "beats": sum(1 for p in prints if (p["surprise_pct"] or 0) > 0),
            "of": len(prints),
            "avg_surprise_pct": round(sum(p["surprise_pct"] for p in prints) / len(prints), 2) if prints else None,
        },
        # Price action. Present in the real cache, and the packet must drop it.
        "reactions": {
            "available": True,
            "prints": [{"report_date": "2026-07-30", "move_pct": 4.87},
                       {"report_date": "2026-04-30", "move_pct": -2.13}],
            "avg_abs_move_pct": 3.5,
            "down_prints": 1,
            "of": 2,
        },
    }


def _write_exp(payload: dict) -> None:
    from ptm.config import data_dir

    path = data_dir("raw", "expectations", f"{payload['ticker']}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _qrow(ticker: str, **kw) -> dict:
    """A quant table row — note `price`, which the packet must not carry."""
    row = {
        "ticker": ticker, "name": f"{ticker} Inc.", "sector": "Industrials",
        "industry": "Aerospace", "price": 139.86, "market_cap": 1.7e10,
        "revenue": 9.0e9, "ps": 1.96, "eps1": 12.4, "eps2": 12.78,
        "eg1": 0.034, "eg2": 0.031, "pe1": 11.28, "pe2": 10.94,
        "peg1": 3.30, "peg2": 3.54, "pe_vs_theme": 0.34, "peg_vs_theme": 3.08,
        "flag": "mixed", "flag_detail": "P/E 0.3x theme median vs PEG 3.1x theme median",
        "earnings_date": "2026-11-05", "days_to_print": 64,
    }
    row.update(kw)
    return row


def _theme_row(tickers: list[str]) -> dict:
    return {
        "theme": "aerospace engineering",
        "status": "ACTIVE",
        "lean": "long",
        "breadth": 0.5,
        "thesis": "defence order flow re-rating",
        "bellwether": tickers[0] if tickers else None,
        "members": [
            {"ticker": t, "covered": True, "rev90": None, "up30": None, "down30": None,
             "earnings_date": "2026-11-05", "days_to_print": 64, "market_cap": 1.7e10}
            for t in tickers
        ],
    }


@pytest.fixture
def three_names():
    """MOG-A rising hard, LDOS rising, WWD falling — one of each direction."""
    _write_exp(_exp_payload("MOGA", rev90=6.1, rev30=1.4, up=7, down=0,
                            surprise=[("2025-09-30", 2.1, 2.0, 5.0), ("2025-12-31", 2.6, 2.4, 8.3),
                                      ("2026-03-31", 3.0, 2.6, 15.4), ("2026-06-30", 3.72, 2.62, 41.98)]))
    _write_exp(_exp_payload("LDOS", rev90=2.4, rev30=0.6, up=4, down=1,
                            surprise=[("2026-06-30", 3.26, 2.91, 12.4)]))
    _write_exp(_exp_payload("WWD", rev90=-1.9, rev30=-0.8, up=1, down=5,
                            surprise=[("2026-06-30", 2.52, 2.44, 3.3)]))
    quant = {t: _qrow(t) for t in ("MOGA", "LDOS", "WWD")}
    quant["MOGA"].update(pe1=24.0, peg1=0.9, flag="premium", pe_vs_theme=1.6, peg_vs_theme=0.9)
    quant["WWD"].update(pe1=38.0, peg1=2.4, flag="premium", pe_vs_theme=2.1, peg_vs_theme=2.0)
    return _theme_row(["MOGA", "LDOS", "WWD"]), quant


# ------------------------------------------------- the packet carries no price

def test_packet_carries_no_price_data_at_all(three_names):
    """The load-bearing omission: no price, no price history, no reactions.

    If any of these leak back in, the pass can write technicals — which is the
    one thing this process is defined not to do.
    """
    from ptm_setups.inputs import member_packet

    theme_row, quant = three_names
    packet = member_packet("MOGA", theme_row["members"][0], quant["MOGA"], REF)
    blob = json.dumps(packet)
    assert "price" not in packet
    assert "reactions" not in packet and "move_pct" not in blob
    assert "avg_abs_move_pct" not in blob
    assert "139.86" not in blob  # the quant row's price never travels
    # valuation is the ONLY channel price may enter through, already a ratio
    assert packet["valuation"]["forward_pe_fy1"] == 24.0
    assert packet["valuation"]["price_to_sales"] == 1.96
    assert "price_to_sales" in packet["valuation"]


def test_packet_reads_surprise_revisions_and_calendar(three_names):
    from ptm_setups.inputs import member_packet

    theme_row, quant = three_names
    packet = member_packet("MOGA", theme_row["members"][0], quant["MOGA"], REF)
    assert packet["eps_surprise"]["last"] == {
        "quarter": "2026-06-30", "quarter_ended": "2026-06-30",
        # the period ALREADY reported, named so it cannot be confused with the
        # period the NEXT print reports (a live pass called this beat "Q3 2026").
        # The label is CALENDAR: Moog's own filings call this same period fiscal
        # Q3, since its year ends in September — hence the end date is primary.
        "calendar_quarter": "Q2 2026",
        "actual": 3.72, "estimate": 2.62, "surprise_pct": 41.98, "low_base": False,
    }
    assert packet["eps_surprise"]["beats"] == 4 and packet["eps_surprise"]["of"] == 4
    assert packet["eps_surprise"]["avg_distorted"] is False  # every quarter has a real base
    assert packet["revisions"]["fy1_change_90d_pct"] == 6.1
    assert packet["revisions"]["analysts_up_30d"] == 7
    # the quarter the print reports is computed, never guessed
    assert packet["next_print"]["reports_quarter"] == "Q3 2026 (quarter ending 2026-09-30)"


def test_surprise_facts_takes_the_latest_quarter_whatever_the_order():
    from ptm_setups.inputs import surprise_facts

    payload = _exp_payload("X", rev90=1.0, surprise=[("2026-06-30", 2.0, 1.0, 100.0),
                                                     ("2025-12-31", 1.0, 1.0, 0.0)])
    payload["surprise"]["prints"].reverse()  # newest first, as some feeds order it
    facts = surprise_facts(payload)
    assert facts["last"]["quarter"] == "2026-06-30"
    assert facts["last"]["surprise_pct"] == 100.0


def test_the_two_quarters_are_named_apart(three_names):
    """A live pass attributed the June beat to "Q3 2026" — the quarter the NEXT
    print reports. Both are now labelled, and the prompt says they differ."""
    from ptm_setups.inputs import member_packet, quarter_label, surprise_cell

    assert quarter_label("2026-06-30") == "Q2 2026"
    assert quarter_label("2026-12-31") == "Q4 2026"
    assert quarter_label("nope") == "" and quarter_label(None) == ""

    theme_row, quant = three_names
    packet = member_packet("MOGA", theme_row["members"][0], quant["MOGA"], REF)
    assert packet["eps_surprise"]["last"]["calendar_quarter"] == "Q2 2026"
    assert packet["eps_surprise"]["last"]["quarter_ended"] == "2026-06-30"
    assert packet["next_print"]["reports_quarter"].startswith("Q3 2026")
    # the cell states the END DATE, which no fiscal calendar can contradict
    assert "quarter ended 2026-06-30" in surprise_cell(packet)


def test_the_prompt_demands_a_non_valuation_reason(three_names, monkeypatch):
    """A live pass ranked a name first for its low P/E, which the rules forbid.

    Every entry now has to name the fundamental fact behind its rank, and that
    field is carried into the row and the markdown so the ordering can be
    audited against it.
    """
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    seen = {}

    def capture(system, user, *a, **k):
        seen["system"], seen["user"] = system, user
        return {"ranking": [{"ticker": "MOGA", "rank": 1, "side": "long",
                             "ranked_on": "largest beat in the group with the only raised guide"}]}

    monkeypatch.setattr(rank, "chat_json", capture)
    out = rank.rank_group(theme_row, quant, REF)
    assert "PROVE THE RANK IS NOT A VALUATION RANK" in seen["system"]
    assert "TWO DIFFERENT QUARTERS" in seen["system"]
    assert "ranked_on" in seen["user"]
    moga = next(r for r in out["ranking"] if r["ticker"] == "MOGA")
    assert moga["ranked_on"] == "largest beat in the group with the only raised guide"


def test_the_answering_model_is_recorded_not_assumed(three_names, monkeypatch):
    """chat_json can quietly fall back to a smaller model; the artifact must say
    which model actually produced the ranking."""
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "glm-5.3-flash")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)

    def fell_back(system, user, *a, **k):
        k["used_out"].append("gpt-oss:20b")  # the provider answered with something else
        return {"ranking": []}

    monkeypatch.setattr(rank, "chat_json", fell_back)
    out = rank.rank_group(theme_row, quant, REF)
    assert out["model"] == "gpt-oss:20b"


def test_an_explicit_model_overrides_the_configured_one(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "glm-5.3-flash")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    asked = {}
    monkeypatch.setattr(rank, "chat_json",
                        lambda s, u, **k: (asked.update(model=k.get("model")), {"ranking": []})[1])
    rank.rank_group(theme_row, quant, REF, model="kimi-k3")
    assert asked["model"] == "kimi-k3"


def test_revision_side_is_a_prior_with_a_dead_band():
    from ptm_setups.inputs import revision_side

    assert revision_side({"revisions": {"fy1_change_90d_pct": 6.1}}) == "long"
    assert revision_side({"revisions": {"fy1_change_90d_pct": -1.9}}) == "short"
    assert revision_side({"revisions": {"fy1_change_90d_pct": 0.3}}) == "flat"
    assert revision_side({"revisions": {"fy1_change_90d_pct": None}}) == "none"


def test_a_name_with_no_fundamental_data_is_skipped_not_ranked():
    from ptm_setups.inputs import has_anything_to_rank, member_packet

    packet = member_packet("EMPTY", {"ticker": "EMPTY", "covered": False}, {}, REF)
    assert not has_anything_to_rank(packet)
    good = member_packet("X", {"ticker": "X", "rev90": 3.0}, {}, REF)
    assert has_anything_to_rank(good)


# --------------------------------------------------- the factual table columns

def test_table_cells_are_rendered_from_the_packet(three_names):
    from ptm_setups.inputs import member_packet, setup_cell, surprise_cell, valuation_cell

    theme_row, quant = three_names
    packet = member_packet("MOGA", theme_row["members"][0], quant["MOGA"], REF)
    surprise = surprise_cell(packet)
    assert "+41.98% EPS beat" in surprise
    assert "$3.72 vs $2.62 est" in surprise
    assert "beat 4 of 4" in surprise
    setup = setup_cell(packet)
    assert "FY1 est +6.1% 90d" in setup and "+1.4% 30d" in setup
    assert "7 up / 0 down 30d" in setup
    assert "prints 2026-11-05 (64d)" in setup
    val = valuation_cell(packet)
    assert "PE1 24.0x" in val and "premium vs industry" in val
    # no price and no trend language anywhere in the computed cells
    for cell in (surprise, setup, val):
        assert "139.86" not in cell
        for banned in ("RSI", "moving average", "50-day", "200-day", "support", "resistance"):
            assert banned.lower() not in cell.lower()


def test_a_percentage_off_a_near_zero_base_is_flagged_not_ranked():
    """HTLD's real print: $0.14 against a -$0.01 estimate, an honest +2445%.

    The percentage is an artefact of the denominator, so the packet flags it and
    both the cell and the prompt push the reader to the dollar figures. Without
    this a loss-to-profit swing outranks every genuine beat in the industry.
    """
    from ptm_setups.inputs import low_base, member_packet, setup_cell, surprise_cell

    assert low_base(0.14, -0.01) is True    # near-zero denominator
    assert low_base(0.60, -0.40) is True    # straddles zero: the sign is meaningless
    assert low_base(3.72, 2.62) is False    # a real base, a real percentage
    assert low_base(3.72, None) is False

    payload = _exp_payload("HTLD", rev90=1369.5, rev30=409.3,
                           surprise=[("2026-06-30", 0.14, -0.01, 2445.06)])
    payload["revisions"].update(eps_current=0.29, eps_d30=0.06, eps_d90=0.02)
    _write_exp(payload)
    packet = member_packet("HTLD", {"ticker": "HTLD", "rev90": 1369.5}, _qrow("HTLD"), REF)
    assert packet["eps_surprise"]["last"]["low_base"] is True
    assert packet["revisions"]["low_base"] is True
    assert packet["revisions"]["fy1_eps_90d_ago"] == 0.02  # the levels travel too
    assert packet["revisions"]["fy1_eps_now"] == 0.29
    cell = surprise_cell(packet)
    assert "2445" not in cell            # the artefact percentage is never shown
    assert cell.startswith("**$0.14 vs $-0.01 est**")  # the figures lead instead
    assert "loss to profit" in cell
    assert "artefact of a near-zero base" in cell
    assert "avg n/a (a quarter's % is base-distorted)" in cell  # and the average with it
    setup = setup_cell(packet)
    assert "$0.02 → $0.29 over 90d" in setup
    assert "1369.5" not in setup  # the artefact percentage is not shown at all


def test_the_prompt_warns_about_near_zero_bases(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    seen = {}
    monkeypatch.setattr(rank, "chat_json",
                        lambda system, user, *a, **k: (seen.update(system=system), {"ranking": []})[1])
    rank.rank_group(theme_row, quant, REF)
    assert "PERCENTAGES OFF A NEAR-ZERO BASE" in seen["system"]
    assert "must NEVER outrank a genuine beat" in seen["system"]


def test_surprise_cell_handles_a_miss_and_missing_data():
    from ptm_setups.inputs import surprise_cell

    assert "-9.57% EPS miss" in surprise_cell(
        {"eps_surprise": {"available": True, "last": {"quarter": "2026-03-31", "actual": 1.4,
                                                      "estimate": 1.55, "surprise_pct": -9.57}}}
    )
    assert surprise_cell({"eps_surprise": {"available": False, "last": None}}) == "—"


# ------------------------------------------------------------- the group pass

def test_rank_group_without_an_llm_keeps_the_numbers_and_drops_the_ranking(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: False)
    out = rank.rank_group(theme_row, quant, REF)
    assert out["llm_used"] is False
    assert out["members_ranked"] == 3
    assert len(out["ranking"]) == 3
    assert all(r["side"] == "avoid" for r in out["ranking"])  # no side is invented
    # the measured columns survive; only the judgement is missing
    assert "+41.98% EPS beat" in out["ranking"][0]["surprise_cell"]
    assert all(not r["catalyst"] and not r["setup"] for r in out["ranking"])
    assert "unavailable" in out["headline"]


def test_rank_group_renumbers_the_models_order_and_keeps_dropped_names(three_names, monkeypatch):
    """Trust the model's ORDER, not its integers — and never lose a member."""
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    payload = {
        "headline": "MOGA is the strongest long into the print.",
        "tactical": "Add MOGA first, LDOS on evidence.",
        "ranking": [
            # ties and gaps: 7, 7, and WWD omitted entirely
            {"ticker": "LDOS", "rank": 7, "side": "long", "label": "Rebound",
             "conviction": "medium", "guidance_valuation": "raised FY26 guide",
             "catalyst": "guide raise", "setup": "next two quarters", "risk": "contract timing"},
            {"ticker": "MOGA", "rank": 7, "side": "long", "label": "Strongest long",
             "conviction": "high", "guidance_valuation": "order flow supports the multiple",
             "catalyst": "order book", "setup": "backlog conversion", "risk": "supply chain"},
        ],
    }
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: payload)
    out = rank.rank_group(theme_row, quant, REF)
    assert out["llm_used"] is True and out["model"] == "test-model"
    assert [r["ticker"] for r in out["ranking"]] == ["LDOS", "MOGA", "WWD"]
    assert [r["rank"] for r in out["ranking"]] == [1, 2, 3]  # renumbered, no ties
    dropped = out["ranking"][-1]
    assert dropped["ticker"] == "WWD" and dropped["side"] == "avoid"
    assert "not covered by the ranking pass" in dropped["risk"]
    assert "+3.30% EPS beat" in dropped["surprise_cell"]  # measured columns still there
    # the model's prose and the computed multiples share one cell
    moga = next(r for r in out["ranking"] if r["ticker"] == "MOGA")
    assert moga["guidance_valuation"] == "order flow supports the multiple"
    assert "PE1 24.0x" in moga["guidance_valuation_cell"]


def test_against_revisions_is_computed_not_taken_from_the_model(three_names, monkeypatch):
    """WWD's own estimates are falling; a long call on it must be flagged even
    when the model claims otherwise."""
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: {
        "headline": "h",
        "ranking": [
            {"ticker": "WWD", "rank": 1, "side": "long", "against_revisions": False,
             "label": "Contrarian long", "conviction": "low", "catalyst": "c", "setup": "s", "risk": "r"},
            {"ticker": "MOGA", "rank": 2, "side": "long", "label": "Long", "conviction": "high"},
            {"ticker": "LDOS", "rank": 3, "side": "short", "label": "Short", "conviction": "low"},
        ],
    })
    out = rank.rank_group(theme_row, quant, REF)
    by = {r["ticker"]: r for r in out["ranking"]}
    assert by["WWD"]["revision_prior"] == "short"
    assert by["WWD"]["against_revisions"] is True   # model said False; computed wins
    assert by["MOGA"]["against_revisions"] is False  # long on a rising name
    assert by["LDOS"]["against_revisions"] is True   # short on a rising name


def test_a_bad_side_or_conviction_degrades_instead_of_passing_through(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: {
        "ranking": [{"ticker": "MOGA", "rank": 1, "side": "BUY NOW", "conviction": "enormous"}],
    })
    out = rank.rank_group(theme_row, quant, REF)
    moga = next(r for r in out["ranking"] if r["ticker"] == "MOGA")
    assert moga["side"] == "avoid" and moga["conviction"] == "medium"


def test_a_failed_call_keeps_the_measured_table(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(rank, "chat_json", boom)
    out = rank.rank_group(theme_row, quant, REF)
    assert out["llm_used"] is False
    assert len(out["ranking"]) == 3
    assert "failed" in out["headline"]


def test_the_prompt_shows_the_priors_and_forbids_price(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    seen = {}

    def capture(system, user, *a, **k):
        seen["system"], seen["user"] = system, user
        return {"ranking": []}

    monkeypatch.setattr(rank, "chat_json", capture)
    rank.rank_group(theme_row, quant, REF)
    assert "MOGA=long" in seen["user"] and "WWD=short" in seen["user"]
    assert "prior you may override" in seen["user"]
    assert "NO TECHNICALS AND NO PRICE ACTION" in seen["system"]
    assert "Never rank a name up because it is cheap" in seen["system"]
    assert "2026-09-02" in seen["user"]  # period discipline needs today's date
    assert "139.86" not in seen["user"]  # no price reaches the model


# ------------------------------------------- the best long / best short pair

def _payload_with_picks(**kw):
    base = {
        "headline": "h",
        "tactical": "work the calendar",
        "ranking": [{"ticker": "MOGA", "rank": 1, "side": "long", "label": "L", "conviction": "high"},
                    {"ticker": "WWD", "rank": 2, "side": "short", "label": "S", "conviction": "medium"}],
        "best_long": {"ticker": "MOGA", "thesis": "long thesis", "catalyst": "long catalyst",
                      "setup": "long setup", "risk": "long risk", "conviction": "high"},
        "best_short": {"ticker": "WWD", "thesis": "short thesis", "catalyst": "short catalyst",
                       "setup": "short setup", "risk": "short risk", "conviction": "medium"},
    }
    base.update(kw)
    return base


def _ranked(theme_row, quant, monkeypatch, payload):
    from ptm_setups import rank

    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr(rank, "setups_reasoning_effort", lambda: "medium")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: payload)
    return rank, rank.rank_group(theme_row, quant, REF)


def test_each_side_gets_its_own_case(three_names, monkeypatch):
    """The long and the short are two trades, so neither reuses the other's
    reasoning, and each carries the measured facts for its own name."""
    theme_row, quant = three_names
    rank, out = _ranked(theme_row, quant, monkeypatch, _payload_with_picks())
    assert out["best_long"]["ticker"] == "MOGA"
    assert out["best_short"]["ticker"] == "WWD"
    assert out["best_long"]["thesis"] == "long thesis"
    assert out["best_short"]["thesis"] == "short thesis"
    # each pick carries the computed columns for ITS OWN name
    assert "+41.98% EPS beat" in out["best_long"]["surprise_cell"]
    assert "+3.30% EPS beat" in out["best_short"]["surprise_cell"]
    # WWD's own revisions are falling, so a short on it is with the prior
    assert out["best_short"]["against_revisions"] is False


def test_the_short_leads_when_the_industry_is_not_rising(three_names, monkeypatch):
    """A flat or falling group's useful answer is which name gets cut, so the
    short section comes first and the ordering is recorded, not just styled."""
    theme_row, quant = three_names
    theme_row["breadth"] = -0.4
    rank, out = _ranked(theme_row, quant, monkeypatch, _payload_with_picks())
    assert out["short_first"] is True
    md = "\n".join(rank._best_pick_md(out))
    assert md.index("## Best short") < md.index("## Best long")
    assert "Best short — the primary call" in md
    assert "Best long — the secondary call" in md


def test_the_long_leads_when_the_industry_is_rising(three_names, monkeypatch):
    theme_row, quant = three_names
    theme_row["breadth"] = 0.67
    rank, out = _ranked(theme_row, quant, monkeypatch, _payload_with_picks())
    assert out["short_first"] is False
    md = "\n".join(rank._best_pick_md(out))
    assert md.index("## Best long") < md.index("## Best short")


def test_an_admitted_absence_beats_an_invented_short(three_names, monkeypatch):
    theme_row, quant = three_names
    payload = _payload_with_picks(best_short={"ticker": None, "thesis": "no member's estimates are rolling over"})
    rank, out = _ranked(theme_row, quant, monkeypatch, payload)
    assert out["best_short"]["ticker"] == ""
    assert "no member's estimates" in out["best_short"]["none_reason"]
    md = "\n".join(rank._best_pick_md(out))
    assert "**None in this industry.**" in md


def test_a_pick_naming_an_outsider_is_dropped(three_names, monkeypatch):
    """A ticker that is not in this industry cannot be given its own case."""
    theme_row, quant = three_names
    payload = _payload_with_picks(best_short={"ticker": "NVDA", "thesis": "not in this group"})
    rank, out = _ranked(theme_row, quant, monkeypatch, payload)
    assert out["best_short"] is None


def test_the_prompt_makes_the_short_the_harder_call(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    theme_row["breadth"] = -0.5
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr(rank, "setups_reasoning_effort", lambda: "medium")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    seen = {}
    monkeypatch.setattr(rank, "chat_json",
                        lambda sy, u, **k: (seen.update(system=sy, user=u), {"ranking": []})[1])
    rank.rank_group(theme_row, quant, REF)
    assert "THE SHORT IS THE HARDER AND MORE VALUABLE CALL" in seen["system"]
    assert "best_long and best_short" in seen["user"]
    # the prompt states this group's breadth and which side leads because of it
    assert "ESTIMATE BREADTH IS -0.50" in seen["user"]
    assert "SHORT is the" in seen["user"]


def test_pick_prose_is_not_cut_mid_word(three_names, monkeypatch):
    from ptm_setups.inputs import clip_words

    long_text = "word " * 400
    theme_row, quant = three_names
    payload = _payload_with_picks(best_long={"ticker": "MOGA", "thesis": long_text, "conviction": "high"})
    _, out = _ranked(theme_row, quant, monkeypatch, payload)
    thesis = out["best_long"]["thesis"]
    assert thesis.endswith("…") and not thesis.endswith("wor…")
    assert clip_words("alpha beta gamma", 100) == "alpha beta gamma"  # short text untouched
    assert clip_words("alpha beta gamma", 12).endswith("…")


def test_an_empty_first_pass_is_retried_at_low_effort(three_names, monkeypatch):
    """A thinking model can spend the whole budget and answer with nothing.

    Measured live: a five-name group at medium effort returned no ranking at
    all. The retry drops thinking to low and lifts the budget to the ceiling,
    so the industry gets a ranking instead of an empty table.
    """
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr(rank, "setups_reasoning_effort", lambda: "medium")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    calls = []

    def flaky(system, user, **kw):
        calls.append((kw.get("reasoning_effort"), kw.get("max_tokens")))
        if len(calls) == 1:
            return {}  # what an out-of-budget thinking model actually returns
        return {"headline": "h", "ranking": [{"ticker": "MOGA", "rank": 1, "side": "long"}]}

    monkeypatch.setattr(rank, "chat_json", flaky)
    out = rank.rank_group(theme_row, quant, REF)
    assert len(calls) == 2
    assert calls[0][0] == "medium"
    assert calls[1] == ("low", rank._TOKENS_CEILING)  # thinking down, budget up
    assert [r["ticker"] for r in out["ranking"]][0] == "MOGA"
    assert out["llm_used"] is True


def test_a_usable_first_pass_is_not_retried(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr(rank, "setups_reasoning_effort", lambda: "medium")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(rank, "chat_json", lambda s, u, **k: (
        calls.append(1), {"ranking": [{"ticker": "MOGA", "rank": 1, "side": "long"}]})[1])
    rank.rank_group(theme_row, quant, REF)
    assert len(calls) == 1  # no second call spent on a good answer


def test_both_passes_failing_still_keeps_the_measured_table(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr(rank, "setups_reasoning_effort", lambda: "medium")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(rank, "chat_json", boom)
    out = rank.rank_group(theme_row, quant, REF)
    assert out["llm_used"] is False
    assert len(out["ranking"]) == 3          # every member still listed
    assert "+41.98% EPS beat" in out["ranking"][0]["surprise_cell"]


# ------------------------------------------------------ the prompt size budget

def test_oversized_packets_are_trimmed_not_sliced():
    """A blunt slice of the JSON would hand the model a malformed object.

    Real industries exceed the budget already (eight members with four EDGAR
    packs ran to 26k), so the filed prose is trimmed until it fits while every
    measured number and every member survives.
    """
    from ptm_setups.rank import _PACKET_CHARS, _fit_packets

    packets = [
        {
            "ticker": f"T{i}",
            "eps_surprise": {"available": True, "last": {"actual": 1.0 + i, "estimate": 1.0,
                                                         "surprise_pct": 10.0 * i, "low_base": False}},
            "valuation": {"forward_pe_fy1": 10.0 + i, "flag": "fair"},
            "revisions": {"fy1_change_90d_pct": float(i)},
            "filed": {
                "edgar_pack_date": "2026-08-25",
                "last_earnings_exhibit": "X" * 1400,
                "forward_guidance_lines": [f"guidance line {n} " + "y" * 120 for n in range(10)],
            },
        }
        for i in range(20)
    ]
    raw = json.dumps(packets)
    assert len(raw) > _PACKET_CHARS  # the fixture reproduces the real overflow

    blob, note = _fit_packets(packets)
    assert len(blob) <= _PACKET_CHARS
    fitted = json.loads(blob)                       # still valid JSON, not a cut string
    assert len(fitted) == len(packets)              # no member silently dropped
    assert note and "abridged" in note              # and the model is told
    for before, after in zip(packets, fitted):      # every number identical
        assert after["eps_surprise"] == before["eps_surprise"]
        assert after["valuation"] == before["valuation"]
        assert after["revisions"] == before["revisions"]
    assert len(fitted[0]["filed"]["last_earnings_exhibit"]) < 1400  # only prose gave way


def test_packets_within_budget_are_untouched():
    from ptm_setups.rank import _fit_packets

    packets = [{"ticker": "A", "revisions": {"fy1_change_90d_pct": 1.0}}]
    blob, note = _fit_packets(packets)
    assert note == "" and json.loads(blob) == packets


def test_an_extreme_group_keeps_the_numbers_and_drops_the_filings():
    """Past every trim level the filed text goes entirely — never the numbers."""
    from ptm_setups.rank import _fit_packets

    packets = [
        {"ticker": f"T{i}", "revisions": {"fy1_change_90d_pct": float(i)},
         "filed": {"last_earnings_exhibit": "X" * 1400,
                   "forward_guidance_lines": ["y" * 300 for _ in range(12)]}}
        for i in range(120)
    ]
    blob, note = _fit_packets(packets)
    fitted = json.loads(blob)
    assert len(fitted) == 120
    assert all("filed" not in p for p in fitted)
    assert all(p["revisions"]["fy1_change_90d_pct"] == float(i) for i, p in enumerate(fitted))
    assert "do not claim to have read any filing" in note


# ------------------------------------------------------- the cross-industry final

def test_final_round_ranks_each_side_and_places_dropped_candidates(monkeypatch):
    from ptm_setups import rank

    candidates = [
        {"ticker": "MOGA", "name": "Moog", "theme": "aerospace", "side": "long", "rank": 1,
         "label": "Strongest long", "conviction": "high", "surprise_pct": 41.98, "rev90": 6.1},
        {"ticker": "AAA", "name": "A", "theme": "software", "side": "long", "rank": 1,
         "label": "Long", "conviction": "medium", "surprise_pct": 5.0, "rev90": 2.0},
        {"ticker": "BBB", "name": "B", "theme": "software", "side": "short", "rank": 4,
         "label": "Short", "conviction": "medium", "surprise_pct": -8.0, "rev90": -3.0},
    ]
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: {
        "summary": "aerospace carries the best long",
        "longs": [{"ticker": "MOGA", "rank": 3, "why": "biggest beat with a raise"}],  # AAA omitted
        "shorts": [{"ticker": "BBB", "rank": 1, "why": "estimates still falling"}],
    })
    out = rank._final_round(candidates, REF)
    assert out["llm_used"] is True
    assert [r["ticker"] for r in out["longs"]] == ["MOGA", "AAA"]
    assert [r["rank"] for r in out["longs"]] == [1, 2]
    assert "not placed" in out["longs"][1]["why"]
    assert out["shorts"][0]["ticker"] == "BBB"


def test_final_prefers_the_industrys_declared_pick_over_the_top_row():
    """Each industry DECLARES a best long and best short with its own thesis;
    the final should rank those, not whichever row happens to sit highest."""
    from ptm_setups.rank import _final_candidates

    groups = [{
        "theme": "aerospace", "llm_used": True, "short_first": False,
        "best_long": {"ticker": "B", "thesis": "declared long thesis"},
        "best_short": {"ticker": "C", "thesis": "declared short thesis"},
        "ranking": [
            {"ticker": "A", "side": "long", "rank": 1},   # top row, NOT the declared pick
            {"ticker": "B", "side": "long", "rank": 2},
            {"ticker": "C", "side": "short", "rank": 3},
        ],
    }]
    picked = _final_candidates(groups)
    by = {c["side"]: c for c in picked}
    assert by["long"]["ticker"] == "B"          # the declared pick wins
    assert by["long"]["thesis"] == "declared long thesis"
    assert by["long"]["declared"] is True
    assert by["short"]["ticker"] == "C"
    # a rising group's primary side is the long
    assert by["long"]["primary_side"] == "long"


def test_final_falls_back_to_the_top_row_when_nothing_was_declared():
    from ptm_setups.rank import _final_candidates

    groups = [{
        "theme": "aerospace", "llm_used": True, "short_first": True,
        "best_long": None, "best_short": {"ticker": None, "thesis": "no credible short"},
        "ranking": [{"ticker": "A", "side": "long", "rank": 1},
                    {"ticker": "C", "side": "short", "rank": 2}],
    }]
    picked = _final_candidates(groups)
    by = {c["side"]: c for c in picked}
    assert by["long"]["ticker"] == "A" and by["long"]["declared"] is False
    assert by["short"]["ticker"] == "C"
    assert by["short"]["primary_side"] == "short"  # the group led with the short


def test_final_candidates_takes_one_long_and_one_short_per_industry():
    from ptm_setups.rank import _final_candidates

    groups = [{
        "theme": "aerospace", "llm_used": True, "ranking": [
            {"ticker": "A", "side": "long", "rank": 1}, {"ticker": "B", "side": "long", "rank": 2},
            {"ticker": "C", "side": "short", "rank": 3}, {"ticker": "D", "side": "avoid", "rank": 4},
        ],
    }, {
        "theme": "unranked group", "llm_used": False, "ranking": [{"ticker": "Z", "side": "long", "rank": 1}],
    }]
    picked = _final_candidates(groups)
    assert [c["ticker"] for c in picked] == ["A", "C"]  # best of each side, unranked group excluded


# --------------------------------------------------------------------- markdown

def test_group_markdown_has_the_table_the_per_name_case_and_no_price(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: {
        "headline": "**MOGA** is the strongest 1-3 month long setup.",
        "tactical": "Prioritise MOGA into the print.",
        "ranking": [
            {"ticker": "MOGA", "rank": 1, "side": "long", "label": "Strongest long", "conviction": "high",
             "guidance_valuation": "raised FY26 guide", "catalyst": "order book converts",
             "setup": "backlog into FY27", "risk": "supply chain"},
            {"ticker": "WWD", "rank": 2, "side": "short", "label": "Weakest", "conviction": "medium",
             "guidance_valuation": "guide intact but demanding", "catalyst": "margin mix",
             "setup": "aftermarket normalises", "risk": "aftermarket stays hot"},
            {"ticker": "LDOS", "rank": 3, "side": "short", "label": "Fading", "conviction": "low",
             "catalyst": "book-to-bill rolls", "setup": "next two quarters", "risk": "its own estimates are still rising"},
        ],
    })
    group = rank.rank_group(theme_row, quant, REF)
    path = rank._group_md(group, REF)
    text = path.read_text(encoding="utf-8")
    assert path.name == "_RANKING_2026-09-02.md"
    assert path.parent.name == "aerospace_engineering"
    assert "| # | Ticker | Latest earnings surprise |" in text
    assert "**+41.98% EPS beat**" in text
    assert "**1. MOGA (MOGA Inc.) — Strongest long** · long · conviction high" in text
    assert "* **The catalyst:** order book converts" in text
    assert "Tactical trade idea:** Prioritise MOGA into the print." in text
    assert "⚠ against its own revisions (long prior)" in text  # the LDOS short opposes its rising estimates
    assert "no technicals" in text and "Cheapness is not a catalyst" in text
    assert "139.86" not in text


def test_leaderboard_markdown_lists_both_sides_and_links_the_industries(three_names, monkeypatch):
    from ptm_setups import rank

    theme_row, quant = three_names
    monkeypatch.setattr(rank, "llm_available", lambda: True)
    monkeypatch.setattr(rank, "setups_model", lambda: "test-model")
    monkeypatch.setattr("ptm_setups.search.group_snippets", lambda *a, **k: None)
    monkeypatch.setattr(rank, "chat_json", lambda *a, **k: {
        "headline": "h", "ranking": [
            {"ticker": "MOGA", "rank": 1, "side": "long", "label": "Strongest long", "conviction": "high"},
            {"ticker": "WWD", "rank": 2, "side": "short", "label": "Weakest", "conviction": "medium"},
        ],
    })
    group = rank.rank_group(theme_row, quant, REF)
    payload = {
        "as_of": REF.isoformat(),
        "groups": [group],
        "leaderboard": {"summary": "one industry carries it",
                        "longs": [{"ticker": "MOGA", "theme": "aerospace engineering", "rank": 1, "why": "biggest beat"}],
                        "shorts": [{"ticker": "WWD", "theme": "aerospace engineering", "rank": 1, "why": "falling"}]},
    }
    path = rank._leaderboard_md(payload, REF)
    text = path.read_text(encoding="utf-8")
    assert path.name == "_LEADERBOARD_2026-09-02.md"
    assert "## Best longs" in text and "## Best shorts" in text
    assert "**MOGA**" in text and "biggest beat" in text
    assert "aerospace_engineering/_RANKING_2026-09-02.md" in text


# --------------------------------------------------------------------- search

def test_search_pools_the_budget_per_industry_not_per_name(monkeypatch):
    """Two industry queries plus one per member — not two per member."""
    from ptm_setups import search

    monkeypatch.setattr("ptm.deepsearch.web.available", lambda: True)
    calls = []

    def fake_search(query, max_results=5):
        calls.append(query)
        return [{"title": "t", "url": f"http://x/{len(calls)}", "content": "c"}]

    monkeypatch.setattr("ptm.deepsearch.web.web_search", fake_search)
    members = [{"ticker": t, "name": f"{t} Inc."} for t in ("A", "B", "C")]
    out = search.group_snippets("aerospace engineering", members, REF)
    assert len(calls) == 5  # 2 industry + 3 members
    assert "aerospace engineering industry earnings season 2026" in calls[0]
    assert "A Inc. A guidance outlook" in calls[2]
    assert out["queries"] == 5 and len(out["searches"]) == 5


def test_search_is_capped_and_degrades_without_a_key(monkeypatch):
    from ptm_setups import search

    monkeypatch.setattr("ptm.deepsearch.web.available", lambda: False)
    assert search.group_snippets("x", [{"ticker": "A"}], REF) is None

    monkeypatch.setattr("ptm.deepsearch.web.available", lambda: True)
    monkeypatch.setattr(search, "MAX_QUERIES_PER_GROUP", 4)
    calls = []
    monkeypatch.setattr("ptm.deepsearch.web.web_search",
                        lambda q, max_results=5: (calls.append(q), [])[1])
    members = [{"ticker": t} for t in ("A", "B", "C", "D", "E")]
    assert search.group_snippets("theme", members, REF) is None  # no snippets came back
    assert len(calls) == 4  # capped, not 7


def test_search_survives_a_dead_endpoint(monkeypatch):
    from ptm_setups import search

    monkeypatch.setattr("ptm.deepsearch.web.available", lambda: True)

    def flaky(query, max_results=5):
        if "industry earnings season" in query:
            raise RuntimeError("429")
        return [{"title": "ok", "url": "http://x", "content": "c"}]

    monkeypatch.setattr("ptm.deepsearch.web.web_search", flaky)
    out = search.group_snippets("theme", [{"ticker": "A"}], REF)
    assert out and out["queries"] == 2  # one industry query died, the rest ran


# ------------------------------------------------------------------- the sweep

def test_run_setups_refuses_without_a_quant_table(monkeypatch):
    from ptm.config import data_dir
    from ptm_setups.rank import run_setups

    path = data_dir("simple", "theme_map.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "source": "xlsx clusters", "theme_count": 1, "ticker_count": 1,
        "themes": [{"theme": "t", "members": ["AAA"]}],
    }), encoding="utf-8")
    with pytest.raises(SystemExit, match="no quant table"):
        run_setups(source="manual", ref=REF)
