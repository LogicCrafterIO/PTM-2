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
    """Every prompt in the layer, not just the last one."""
    captured = []

    def fake_chat(system, user, **kwargs):
        captured.append((system, user))
        return {"summary": "s", "narrative": "n", "views": [], "ranked_tickers": [], "contradictions": []}

    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr("ptm.group_review.chat_json", fake_chat)
    group_review("sector", "Industrials", [_idea("AAA", Side.LONG, True)], as_of="2026-08-18")
    assert len(captured) >= 2, "a view pass and a synthesis pass"
    for system, user in captured:
        low = system.lower()
        assert "technical analysis" in low
        assert "must not reason" in low or "no price data" in low
        for token in ("ret_60d", "momentum\":", "direction\":"):
            assert token not in user


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
        lambda system, user, **kwargs: {
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
    def boom(system, user, **kwargs):
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
    for token in ("GroupReview", "group_review"):
        assert token not in source, f"{token} must not reach a gate or the book"


def test_no_price_derived_signal_reaches_a_gate_or_the_book():
    """This guard used to ban the bare words "momentum", "direction" and
    "aligned". That was a proxy for the real rule - no technical analysis - and
    the proxy expired: "revision momentum" now means analyst estimate revisions,
    which are a fundamental input, and filing "direction" is a reading of a
    filing. Both are legitimate.

    So the guard tests the actual prohibition instead, and is stricter for it:
    no price-derived construct may influence inclusion or sizing.
    """
    import re

    from ptm import book, gates

    source = (inspect.getsource(gates) + inspect.getsource(book)).lower()
    # Word-bounded: a bare substring search matched "sma" inside "small numbers"
    # and "ema" inside "demand", which would have made this guard unfixable
    # noise rather than a check.
    for token in (
        "sma", "ema", "macd", "tape", "atr", "stop_pct", "target_pct", "r_score",
        "close_to_close", "price action", "moving average", "relative strength",
        "trailing return",
    ):
        assert not re.search(rf"\b{re.escape(token)}\b", source), (
            f"{token!r} is technical analysis and must not gate a name"
        )
    # And nothing may read a price series to decide membership.
    for token in ("prices.csv", "read_df(data_dir"):
        assert token not in source, f"{token!r} reads prices inside a gate"


def test_large_groups_are_chunked_so_every_name_is_covered(monkeypatch):
    """A 137-name group came back with 8 comments and 129 placeholders. Views are
    now requested in chunks small enough for the model to answer in full."""
    from ptm.group_review import VIEW_CHUNK

    calls = []

    def fake_chat(system, user, **kwargs):
        calls.append(user)
        if "views (array of {ticker, comment})" in user:
            # Echo back exactly the tickers this chunk asked for.
            line = [ln for ln in user.splitlines() if ln.startswith("Cover all ")][0]
            tickers = line.split(":", 1)[1].strip().split(", ")
            return {"views": [{"ticker": t, "comment": f"note on {t}"} for t in tickers]}
        return {"summary": "s", "narrative": "n", "ranked_tickers": [], "contradictions": []}

    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr("ptm.group_review.chat_json", fake_chat)

    ideas = [_idea(f"T{i:03d}", Side.LONG, supports=True) for i in range(40)]
    review = group_review("sector", "Industrials", ideas, as_of="2026-08-18")

    assert review.covered == 40, f"only {review.covered}/40 covered"
    assert not any(v.comment == "not covered by the group LLM pass" for v in review.views)
    # ceil(40/12) view calls + 1 synthesis
    assert len(calls) == (40 + VIEW_CHUNK - 1) // VIEW_CHUNK + 1


def test_partial_ranking_is_disclosed_not_disguised(monkeypatch):
    """Padding the model's short ranking with the rest made it look complete."""
    def fake_chat(system, user, **kwargs):
        if "views (array of {ticker, comment})" in user:
            return {"views": []}
        return {"summary": "s", "narrative": "n", "ranked_tickers": ["T000", "T001"], "contradictions": []}

    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr("ptm.group_review.chat_json", fake_chat)
    ideas = [_idea(f"T{i:03d}", Side.LONG, supports=True) for i in range(10)]
    review = group_review("sector", "Industrials", ideas, as_of="2026-08-18")

    assert review.ranked_by_model == 2
    assert len(review.ranked_tickers) == 10
    text = render_group_review(review)
    assert "ranked the first 2" in text
    assert "0/10 names individually reviewed" in text


def test_a_failed_chunk_does_not_lose_the_other_chunks(monkeypatch):
    state = {"n": 0}

    def fake_chat(system, user, **kwargs):
        if "views (array of {ticker, comment})" in user:
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("502 upstream")
            line = [ln for ln in user.splitlines() if ln.startswith("Cover all ")][0]
            tickers = line.split(":", 1)[1].strip().split(", ")
            return {"views": [{"ticker": t, "comment": f"note on {t}"} for t in tickers]}
        return {"summary": "s", "narrative": "n", "ranked_tickers": [], "contradictions": []}

    monkeypatch.setattr("ptm.group_review.llm_available", lambda: True)
    monkeypatch.setattr("ptm.group_review.chat_json", fake_chat)
    ideas = [_idea(f"T{i:03d}", Side.LONG, supports=True) for i in range(24)]
    review = group_review("sector", "Industrials", ideas, as_of="2026-08-18")

    assert review.covered == 12, "the surviving chunk must still be recorded"
    assert "502 upstream" in review.error
