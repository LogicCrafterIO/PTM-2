"""Tests for the simple process's valuation flag, the brief period filter, and the group review."""

from __future__ import annotations

import json
from datetime import date


# --- quant flag: theme-relative premium/discount ------------------------------

def _rows(*peg1s, pe1s=None):
    pes = pe1s or [None] * len(peg1s)
    return [
        {"ticker": f"T{i}", "theme": "test theme", "peg1": p, "pe1": e, "ps": 2.0}
        for i, (p, e) in enumerate(zip(peg1s, pes))
    ]


def test_flag_premium_discount_and_fair():
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.5, 1.0, 1.0, 2.0)  # median 1.0
    _flag_rows(rows)
    by = {r["ticker"]: r["flag"] for r in rows}
    assert by["T0"] == "discount"  # 0.5x median
    assert by["T1"] == "fair"
    assert by["T2"] == "fair"
    assert by["T3"] == "premium"  # 2.0x median


def test_flag_mixed_when_both_extremes_present():
    from ptm_simple.quant import _flag_rows

    # T1: P/E 4x the median (premium signal) AND PEG 0.5x (discount signal) -> mixed.
    # T3: P/E 0.5x the median with a fair PEG -> plain discount.
    rows = _rows(1.0, 0.5, 1.0, 1.0, 1.0, pe1s=[10.0, 20.0, 5.0, 2.5, None])
    _flag_rows(rows)
    by = {r["ticker"]: r["flag"] for r in rows}
    assert by["T1"] == "mixed"
    assert by["T3"] == "discount"
    assert by["T4"] == "fair"


def test_flag_needs_a_theme_median():
    from ptm_simple.quant import _flag_rows

    rows = _rows(1.0, 2.0)  # fewer than 3 members with a multiple
    _flag_rows(rows)
    assert all(r["flag"] == "n/a" for r in rows)


def test_quant_flags_do_not_select_anything():
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.4, 1.0, 3.0)
    _flag_rows(rows)
    assert all("score" not in r and "rank" not in r for r in rows)


# --- the brief period filter --------------------------------------------------

ABNB_BACKWARD = [
    "The same Q2 print will reveal how much of the June-July FIFA World Cup demand converted into revenue.",
    "Q2 supply data could show whether the 10-20% listing declines are spreading.",
    "The Q2 report may quantify the cost of EU Regulation 2024/1028.",
]
FORWARD = [
    "The Q3 print will reveal whether international demand held after the World Cup quarter.",
    "After the Q2 margin collapse to 1.8%, Q3 could show early recovery in take rates.",
    "Q4 2026 guidance could confirm the 12-18 month setup.",
    "The Q3 2026 earnings release (likely early November) is the dated catalyst.",
]


def test_brief_filter_drops_points_about_already_made_prints():
    from ptm_simple.brief import _drop_backward_hedges

    kept = _drop_backward_hedges(ABNB_BACKWARD + FORWARD, date(2026, 9, 2))
    for p in ABNB_BACKWARD:
        assert p not in kept


def test_brief_filter_keeps_forward_points():
    from ptm_simple.brief import _drop_backward_hedges

    kept = _drop_backward_hedges(FORWARD, date(2026, 9, 2))
    assert kept == FORWARD


def test_reported_quarter_maps_print_to_its_quarter():
    from ptm_simple.brief import _reported_quarter

    assert _reported_quarter("2026-11-05") == "Q3 2026 (quarter ending 2026-09-30)"
    assert _reported_quarter("2026-08-06") == "Q2 2026 (quarter ending 2026-06-30)"
    assert _reported_quarter("2027-02-10") == "Q4 2026 (quarter ending 2026-12-31)"
    assert _reported_quarter("unknown") == ""
    assert _reported_quarter(None) == ""


# --- the print-focused qual ---------------------------------------------------

def test_print_qual_packet_uses_the_research_pack(isolate_roots):
    """The print brief reads the fresh EDGAR pack — the dive is never in the chain."""
    from ptm.config import data_dir
    from ptm_simple import print_qual

    pack = {
        "run_date": "2026-08-25",
        "mda": "Item 7. Management expects revenue growth of 12-15% next quarter.",
        "earnings_exhibit": "Q2 2026 Revenue $3.6B 17% Y/Y Net Income $816M",
        "reported_changes": ["EPS change, consensus FY1 vs prior year: +31.3%"],
    }
    (data_dir("raw", "research")).mkdir(parents=True, exist_ok=True)
    (data_dir("raw", "research", "T0.json")).write_text(json.dumps(pack), encoding="utf-8")
    inputs = print_qual._pack_inputs("T0")
    assert inputs["run_date"] == "2026-08-25"
    assert "Q2 2026 Revenue" in inputs["last_earnings_exhibit"]
    assert inputs["reported_consensus_changes"] == ["EPS change, consensus FY1 vs prior year: +31.3%"]
    assert inputs["filed_facts"]  # forward MD&A lines are extracted
    assert print_qual._pack_inputs("NOPE") is None


def test_print_brief_is_cached_per_run_date(isolate_roots, monkeypatch):
    from ptm_simple import print_qual

    monkeypatch.setattr(print_qual, "llm_available", lambda: True)
    monkeypatch.setattr(print_qual, "_web_inputs", lambda *a, **k: None)  # no live search in tests
    calls = []

    def fake_chat_json(system, user, *a, **k):
        calls.append(user)
        return {"points": ["The Q3 print will reveal pricing power."], "watch": ["Gross margin > 35%"]}

    monkeypatch.setattr(print_qual, "chat_json", fake_chat_json)
    member = {"ticker": "T0", "rev90": 1.2, "earnings_date": "2026-11-05", "days_to_print": 64}
    first = print_qual.print_brief("T0", "long", member, {}, {}, [], date(2026, 9, 2))
    assert calls and "Q3 2026" in calls[0]  # the quarter the print reports is computed, not guessed
    second = print_qual.print_brief("T0", "long", member, {}, {}, [], date(2026, 9, 2))
    assert second == first and len(calls) == 1  # cached within the run date


def test_web_inputs_degrade_gracefully(isolate_roots, monkeypatch):
    from ptm_simple import print_qual

    monkeypatch.setattr("ptm.deepsearch.web.available", lambda: False)
    assert print_qual._web_inputs("T0", {}) is None  # no key -> no search, never an error


# --- the group review ---------------------------------------------------------

def _theme_row(members: list[tuple[str, float | None]]) -> dict:
    return {
        "theme": "Test Theme",
        "status": "ACTIVE",
        "lean": "long",
        "breadth": 0.5,
        "thesis": "test thesis",
        "bellwether": members[0][0] if members else None,
        "members": [
            {"ticker": t, "covered": rev is not None, "rev90": rev, "days_to_print": 30, "earnings_date": "2026-11-05"}
            for t, rev in members
        ],
    }


def test_review_theme_without_llm_marks_everything_uncertain(isolate_roots, monkeypatch):
    from ptm_simple import group_review
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.5, 1.0, 2.0)
    _flag_rows(rows)
    quant = {r["ticker"]: r for r in rows}
    theme_row = _theme_row([("T0", 1.2), ("T1", -1.0), ("T2", None)])
    monkeypatch.setattr(group_review, "llm_available", lambda: False)
    monkeypatch.setattr("ptm_simple.print_qual.llm_available", lambda: False)
    rev = group_review.review_theme(theme_row, quant, date(2026, 9, 2))
    assert rev["members_reviewed"] == 3  # T2 is flat but flagged -> still reviewed, side-neutral
    assert all(r["verdict"] == "uncertain" for r in rev["reviews"])
    assert rev["llm_used"] is False
    assert rev["print_focus"] == {"T0": {}, "T1": {}, "T2": {}}  # no LLM -> no print briefs
    assert {r["ticker"] for r in rev["reviews"]} == {"T0", "T1", "T2"}
    assert {r["side"] for r in rev["reviews"]} == {"long", "short", "neutral"}


def test_flat_member_gets_a_side_neutral_packet(isolate_roots):
    from ptm_simple import group_review
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.5, 1.0, 2.0)
    _flag_rows(rows)
    packet = group_review._member_packet("T1", None, rows[1], None, {"rev90": 0.3, "covered": True})
    assert packet["side"] == "neutral"
    assert packet["rev90_pct"] == 0.3
    assert packet["reports_quarter"] == ""  # fixture has no print date


def test_flat_member_print_brief_is_side_neutral(isolate_roots, monkeypatch):
    from ptm_simple import print_qual

    monkeypatch.setattr(print_qual, "llm_available", lambda: True)
    monkeypatch.setattr(print_qual, "_web_inputs", lambda *a, **k: None)
    user_lines = []

    def fake_chat_json(system, user, *a, **k):
        user_lines.append(user)
        return {"points": ["A guidance raise would create a long side."], "watch": ["Revisions break above +0.5%"]}

    monkeypatch.setattr(print_qual, "chat_json", fake_chat_json)
    member = {"ticker": "T0", "rev90": 0.3, "earnings_date": "2026-11-05", "days_to_print": 64}
    out = print_qual.print_brief("T0", None, member, {}, {}, [], date(2026, 9, 2))
    assert out
    assert "NONE YET" in user_lines[0] and "Side-neutral brief" in user_lines[0]


def test_review_packet_is_print_focused_not_dive_based(isolate_roots):
    """The packet must carry the fresh print-qual case and NO dive fields."""
    from ptm_simple import group_review
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.5, 1.0, 2.0)
    _flag_rows(rows)
    pq = {"points": ["The Q3 print will reveal margin direction."], "watch": ["Gross margin > 35%"]}
    packet = group_review._member_packet(
        "T0", "long", rows[0], pq,
        {"rev90": 1.2, "up30": 3, "down30": 0, "earnings_date": "2026-11-05", "days_to_print": 64},
    )
    assert packet["next_print_case"] == ["The Q3 print will reveal margin direction."]
    assert packet["kpis_that_decide"] == ["Gross margin > 35%"]
    assert packet["reports_quarter"].startswith("Q")  # Nov 5 print reports Q3 2026
    assert packet["analysts_up30_down30"] == [3, 0]
    for banned in ("dive_stance", "dive_bull", "dive_bear", "brief_points"):
        assert banned not in packet


def _write_expectations(data_dir, revs: dict[str, float | None]) -> None:
    """Expectations caches so the radar marks the members covered (never COLD)."""
    expdir = data_dir("raw", "expectations")
    expdir.mkdir(parents=True, exist_ok=True)
    for t, rev in revs.items():
        payload = {
            "revisions": {"available": rev is not None, "change_90d_pct": rev, "analysts_up_30d": 3, "analysts_down_30d": 0},
            "earnings_date": "2026-11-05",
        }
        (expdir / f"{t}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_group_review_writes_markdown_and_aggregate(isolate_roots, monkeypatch):
    from ptm.config import data_dir
    from ptm_simple import group_review
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.5, 1.0, 2.0, 0.8)
    _flag_rows(rows)
    quant_path = group_review.simple_dir("quant_2026-09-02.json")
    quant_path.write_text(json.dumps({"as_of": "2026-09-02", "themes": ["Test Theme"], "rows": rows}), encoding="utf-8")
    theme_map = {"source": "wiki", "themes": [{"theme": "Test Theme", "members": ["T0", "T1", "T2", "T3"]}]}
    (data_dir("simple", "theme_map_wiki.json")).write_text(json.dumps(theme_map), encoding="utf-8")
    # two up, one down, one uncached: breadth (2-1)/3 = 0.33 -> WARM, never COLD
    _write_expectations(data_dir, {"T0": 1.2, "T1": -1.0, "T3": 0.9})

    monkeypatch.setattr(group_review, "llm_available", lambda: False)
    monkeypatch.setattr("ptm_simple.print_qual.llm_available", lambda: False)
    out = group_review.run_group_review(source="wiki", ref=date(2026, 9, 2))
    assert out["themes"] == 1 and out["markdown"] == 1
    saved = json.loads(group_review.simple_dir("group_review_2026-09-02.json").read_text(encoding="utf-8"))
    assert saved["themes"][0]["theme"] == "Test Theme"
    md = list((data_dir().parent / "ideas" / "simple").rglob("_GROUP_REVIEW_*.md"))
    assert md and "Group review" in md[0].read_text(encoding="utf-8")


# --- the trade tag (deterministic side × flag × verdict) ----------------------

def test_trade_tag_four_aligned_combinations():
    from ptm_simple.group_review import _trade_tag

    assert _trade_tag("long", "premium", "justified") == "aligned"
    assert _trade_tag("long", "discount", "not justified") == "aligned"
    assert _trade_tag("short", "discount", "justified") == "aligned"
    assert _trade_tag("short", "premium", "not justified") == "aligned"
    assert _trade_tag("long", "premium", "not justified") == "contradicted"
    assert _trade_tag("long", "discount", "justified") == "contradicted"
    assert _trade_tag("short", "premium", "justified") == "contradicted"
    assert _trade_tag("short", "discount", "not justified") == "contradicted"
    assert _trade_tag("long", "fair", "justified") == "aligned"   # pricing matches the fundamentals
    assert _trade_tag("short", "fair", "justified") == "aligned"
    assert _trade_tag("long", "mixed", "justified") == "aligned"  # both ratios check out
    assert _trade_tag("short", "mixed", "justified") == "aligned"
    assert _trade_tag("long", "fair", "not justified") == "neutral"
    assert _trade_tag("long", "mixed", "not justified") == "neutral"
    assert _trade_tag("neutral", "premium", "justified") == "neutral"
    assert _trade_tag("long", "premium", "uncertain") == "neutral"
    assert _trade_tag("long", "n/a", "justified") == "neutral"


def test_group_review_llm_path_verdicts_are_validated(isolate_roots, monkeypatch):
    from ptm.config import data_dir
    from ptm_simple import group_review, print_qual
    from ptm_simple.quant import _flag_rows

    rows = _rows(0.5, 1.0, 2.0)
    _flag_rows(rows)
    theme_map = {"source": "wiki", "themes": [{"theme": "Test Theme", "members": ["T0", "T1", "T2"]}]}
    (data_dir("simple", "theme_map_wiki.json")).write_text(json.dumps(theme_map), encoding="utf-8")
    quant_path = group_review.simple_dir("quant_2026-09-02.json")
    quant_path.write_text(json.dumps({"as_of": "2026-09-02", "themes": ["Test Theme"], "rows": rows}), encoding="utf-8")
    # two up, one down: breadth (2-1)/2 = 0.5 -> ACTIVE
    _write_expectations(data_dir, {"T0": 1.2, "T1": -1.0, "T2": 0.9})

    monkeypatch.setattr(group_review, "llm_available", lambda: True)
    monkeypatch.setattr(print_qual, "llm_available", lambda: True)
    monkeypatch.setattr(print_qual, "_web_inputs", lambda *a, **k: None)  # no live search in tests
    monkeypatch.setattr(
        print_qual, "chat_json",
        lambda *a, **k: {"points": ["Q3 guidance is the catalyst."], "watch": ["Backlog growth"]},
    )

    def fake_review_call(system, user, *a, **k):
        return {
            "summary": "premiums look thin",
            "reviews": [
                {"ticker": "T0", "verdict": "justified", "reason": "backlog keeps growing into the multiple"},
                {"ticker": "T1", "verdict": "bogus", "reason": "bad verdict word"},
                {"ticker": "T2", "verdict": "justified", "reason": "the premium is earned by forward growth"},
            ],
        }

    monkeypatch.setattr(group_review, "chat_json", fake_review_call)
    out = group_review.run_group_review(source="wiki", ref=date(2026, 9, 2))
    saved = json.loads(group_review.simple_dir("group_review_2026-09-02.json").read_text(encoding="utf-8"))
    by = {r["ticker"]: r for r in saved["themes"][0]["reviews"]}
    assert by["T0"]["verdict"] == "justified"
    assert by["T1"]["verdict"] == "uncertain"  # an unrecognised verdict never passes through
    assert by["T0"]["watch"] == ["Backlog growth"]  # print-qual KPIs ride along for the viewer
    # the deterministic trade tag: T0 is long + discount + justified -> the
    # verdict argues against the side; T2 is long + premium + justified -> aligned
    assert by["T0"]["trade"] == "contradicted"
    assert by["T2"]["trade"] == "aligned"
    assert by["T2"]["printqual"].endswith("printqual_T2_2026-09-02.md")
    assert out["judged"] >= 1