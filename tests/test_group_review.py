import inspect

from ptm.group_review import (
    deterministic_review,
    group_review,
    group_summary,
    name_row,
    render_group_review,
)
from ptm.models import Candidate, QualResult, Side, TradeIdea


def _idea(ticker: str, side: Side, supports=None, sector="Industrials", eg_case="long_case_1_acceleration"):
    return TradeIdea(
        candidate=Candidate(ticker=ticker, name=ticker, sector=sector, side=side, eg_case=eg_case, pe1=12.0, sector_pe1=18.0),
        qual=QualResult(supports_outlier=supports, why=f"{ticker} case", kpis=["backlog"]),
    )


def test_no_price_or_technical_input_reaches_the_prompt():
    """The group layer must carry no tape: no returns, no momentum, no TA."""
    row = name_row(_idea("AAA", Side.LONG, supports=True))
    banned = {
        "ret_20d", "ret_60d", "ret_120d", "direction", "aligned", "vol_20d",
        "pct_from_52w_high", "pct_from_52w_low", "last_close", "price", "sma", "macd",
    }
    assert not (banned & set(row)), f"price data leaked into the group prompt: {banned & set(row)}"
    assert set(row) >= {"ticker", "side", "eg_case", "qual_verdict", "qual_why"}


def test_momentum_module_is_gone():
    import importlib

    for name in ("ptm.momentum",):
        try:
            importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{name} should have been removed")


def test_prompt_forbids_technical_reasoning(monkeypatch):
    captured = {}

    def fake_chat(system, user):
        captured["system"] = system
        captured["user"] = user
        return {"summary": "s", "narrative": "n", "views": [], "ranked_tickers": [], "contradictions": []}

    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr("ptm.group_review.chat_json", fake_chat)
    group_review("sector", "Industrials", [_idea("AAA", Side.LONG, True)], as_of="2026-08-18")
    system = captured["system"].lower()
    assert "technical analysis" in system
    assert "must not reason about price" in system or "no price data" in system
    for token in ("ret_60d", "momentum\":", "direction\":"):
        assert token not in captured["user"]


def test_summary_counts_are_measured_not_modelled():
    rows = [
        name_row(_idea("AAA", Side.LONG, supports=True)),
        name_row(_idea("BBB", Side.SHORT, supports=False)),
        name_row(_idea("CCC", Side.LONG, supports=None)),
    ]
    summary = group_summary(rows)
    assert "3 names (2L/1S)" in summary
    assert "1 support / 1 deny" in summary


def test_deterministic_review_orders_by_qualitative_verdict():
    rows = [
        name_row(_idea("DENY", Side.LONG, supports=False)),
        name_row(_idea("PASS", Side.LONG, supports=True)),
        name_row(_idea("MAYBE", Side.LONG, supports=None)),
    ]
    review = deterministic_review("sector", "Industrials", rows, "2026-08-18", "test")
    assert review.llm_used is False
    assert review.ranked_tickers == ["PASS", "MAYBE", "DENY"]


def test_llm_cannot_revise_the_first_pass_verdict(monkeypatch):
    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr(
        "ptm.group_review.chat_json",
        lambda system, user: {
            "summary": "x",
            "narrative": "y",
            # The group model tries to flip a denied name to a pass.
            "views": [{"ticker": "DENY", "qual_verdict": "supports", "comment": "looks fine to me"}],
            "ranked_tickers": ["DENY"],
            "contradictions": [],
        },
    )
    review = group_review("sector", "Industrials", [_idea("DENY", Side.LONG, supports=False)], as_of="2026-08-18")
    assert review.llm_used is True
    assert review.views[0].qual_verdict == "denies"
    assert review.views[0].comment == "looks fine to me"


def test_llm_failure_degrades_to_deterministic(monkeypatch):
    def boom(system, user):
        raise RuntimeError("502 upstream")

    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr("ptm.group_review.chat_json", boom)
    review = group_review("sector", "Industrials", [_idea("AAA", Side.LONG, True)], as_of="2026-08-18")
    assert review.llm_used is False
    assert "502 upstream" in review.error


def test_render_has_no_tape_section():
    rows = [name_row(_idea("AAA", Side.LONG, supports=True))]
    text = render_group_review(deterministic_review("sector", "Industrials", rows, "2026-08-18", "test"))
    assert "not a gate" in text
    assert "No price or technical input" in text
    assert "## Tape" not in text
    for word in ("momentum", "60d", "tape"):
        assert word not in text.lower().replace("no price or technical input", "")
    assert "| Ticker | Side | EG case | Qualitative | Comment |" in text


def test_group_review_is_not_wired_into_any_gate():
    from ptm import book, gates

    source = inspect.getsource(gates) + inspect.getsource(book)
    for token in ("GroupReview", "group_review", "momentum", "direction", "aligned"):
        assert token not in source
