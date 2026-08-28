"""Second LLM pass: read a whole group of ideas against each other.

The per-name work in ptm/llm.py judges one company in isolation, which means
nothing ever asks whether two ideas in the same sector are making the same
argument, or contradicting one another. This layer takes every idea that shares
a sector (or an earnings window) and reads their fundamental cases side by side.

There is deliberately **no price or technical input here** — no returns, no
moving averages, no momentum. Technical analysis takes no part in screening,
and this layer is part of the research output, so it carries none either.

It is commentary, not a gate: nothing downstream reads a GroupReview to include
or drop a name. See docs/FEATURE-LIMITATIONS.md.
"""

from __future__ import annotations

import json

from ptm.llm import JSON_HINT, _clip, chat_json, llm_available
from ptm.models import GroupNameView, GroupReview, TradeIdea

# Models stop enumerating long lists well before they run out of tokens: asked
# to comment on a 137-name group, one returned 8 entries and the rest silently
# fell back to a placeholder. Per-name views are therefore requested in chunks,
# and the narrative is a separate synthesis pass over compact per-name lines.
# Coverage is recorded so a partial pass can never look like a complete one.
VIEW_CHUNK = 12


def _qual_verdict(idea: TradeIdea) -> str:
    if idea.qual is None:
        return "none"
    if idea.qual.supports_outlier is True:
        return "supports"
    if idea.qual.supports_outlier is False:
        return "denies"
    return "undecided"


def name_row(idea: TradeIdea) -> dict:
    """Compact per-name payload for the group prompt. Fundamentals only."""
    cand = idea.candidate
    row = {
        "ticker": cand.ticker,
        "side": cand.side.value,
        "sector": cand.sector,
        "industry": cand.industry,
        "eg_case": cand.eg_case,
        "eg1": cand.eg1,
        "eg2": cand.eg2,
        "pe1": cand.pe1,
        "sector_pe1": cand.sector_pe1,
        "industry_pe1": cand.industry_pe1,
        "peg1": cand.peg1,
        "ism_tilt": cand.ism_tilt,
        "ism_why": _clip(cand.ism_why, 200),
        "qual_verdict": _qual_verdict(idea),
        "qual_why": _clip(idea.qual.why or idea.qual.summary, 320) if idea.qual else "",
        "operating_plan": _clip(idea.qual.operating_plan, 200) if idea.qual else "",
        "kpis": (idea.qual.kpis or [])[:4] if idea.qual else [],
        "red_flags": (idea.qual.red_flags or [])[:4] if idea.qual else [],
        "gates": list(idea.extra.get("gates") or []),
        "relative_peg": cand.relative_peg,
        "conviction": idea.extra.get("conviction"),
    }
    # Deliberately NOT the implied move or anything else from the option chain.
    # This layer is barred from price input and the ban is enforced by tests; an
    # implied move is derived from option prices, so feeding it here would break
    # the rule the tests exist to protect. Fundamentals only.
    if idea.earnings:
        row["earnings_date"] = idea.earnings.date
        row["earnings_estimated"] = idea.earnings.estimated
    return row


def group_summary(rows: list[dict]) -> str:
    """One deterministic line describing the group, always available."""
    if not rows:
        return "no names"
    longs = sum(1 for r in rows if r["side"] == "long")
    shorts = len(rows) - longs
    supports = sum(1 for r in rows if r["qual_verdict"] == "supports")
    denies = sum(1 for r in rows if r["qual_verdict"] == "denies")
    blocked = sum(1 for r in rows if r["gates"])
    estimated = sum(1 for r in rows if r.get("earnings_estimated"))
    parts = [
        f"{len(rows)} names ({longs}L/{shorts}S)",
        f"qualitative {supports} support / {denies} deny",
        f"{blocked} gated",
    ]
    if estimated:
        parts.append(f"{estimated} on an estimated earnings date")
    return "; ".join(parts)


def _rank_key(row: dict) -> tuple:
    order = {"supports": 0, "undecided": 1, "none": 2, "denies": 3}
    return (order.get(row["qual_verdict"], 3), 1 if row["gates"] else 0, row["ticker"])


def deterministic_review(kind: str, label: str, rows: list[dict], as_of: str, reason: str) -> GroupReview:
    """Group review without an LLM: the measured counts and ordering only."""
    views = [
        GroupNameView(
            ticker=row["ticker"],
            side=row["side"],
            eg_case=row["eg_case"],
            qual_verdict=row["qual_verdict"],
            comment="deterministic: ordered by qualitative verdict, no cross-read performed",
        )
        for row in rows
    ]
    return GroupReview(
        group_kind=kind,
        group_label=label,
        as_of=as_of,
        tickers=[r["ticker"] for r in rows],
        llm_used=False,
        covered=0,
        ranked_by_model=0,
        summary=group_summary(rows),
        narrative=f"LLM skipped ({reason}); no cross-name reading was done.",
        views=views,
        ranked_tickers=[r["ticker"] for r in sorted(rows, key=_rank_key)],
        contradictions=[],
    )


def _chunks(rows: list[dict], size: int) -> list[list[dict]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _view_prompt(axis: str, label: str, rows: list[dict]) -> tuple[str, str]:
    """Ask for one comment per ticker, over a chunk small enough to be answered."""
    system = (
        "You are a long/short portfolio manager reading single-name ideas that share one "
        f"{axis}. For EVERY ticker given, say in one sentence what its case adds relative to the "
        "others, or which name it duplicates. Judge fundamentals and the operating case only. You "
        "are given no price data and must not reason about price action, charts, momentum, moving "
        "averages or entry timing - this process excludes technical analysis. "
        "Return exactly one entry per ticker, no more and no fewer. "
        "Keep every comment under 300 characters. " + JSON_HINT
    )
    tickers = ", ".join(r["ticker"] for r in rows)
    user = (
        "Return JSON key: views (array of {ticker, comment}).\n"
        f"Cover all {len(rows)} tickers: {tickers}\n"
        f"Group: {axis} = {label}\n"
        f"Ideas:\n{json.dumps(rows, default=str)[:9000]}"
    )
    return system, user


def _synthesis_prompt(
    axis: str, label: str, rows: list[dict], macro_bias: str, as_of: str
) -> tuple[str, str]:
    """The cross-read itself, over compact lines so the whole group fits."""
    system = (
        "You are a long/short portfolio manager reviewing a basket of ideas that share one "
        f"{axis}. Do the cross-read nobody has done yet: do these cases agree, duplicate, or "
        "contradict each other? Look for the same thesis repeated across names (a concentrated "
        "a long and a short resting on opposite readings of one industry "
        "driver, a name whose qualitative verdict looks weak beside its peers, and inconsistent "
        "use of the ISM tilt. Fundamentals only: you are given no price data and must not reason "
        "about price action, charts, momentum, moving averages or entry timing - this process "
        "excludes technical analysis. "
        "Keep every string under 300 characters. " + JSON_HINT
    )
    compact = [
        {
            "ticker": r["ticker"],
            "side": r["side"],
            "eg_case": r["eg_case"],
            "pe1": r["pe1"],
            "sector_pe1": r["sector_pe1"],
            "industry_pe1": r.get("industry_pe1"),
            "verdict": r["qual_verdict"],
            "why": (r.get("qual_why") or "")[:120],
            "relative_peg": r.get("relative_peg"),
        }
        for r in rows
    ]
    user = (
        "Return JSON keys: summary (string, one line on what this group is collectively betting "
        "on), narrative (string, 3-6 sentences on how the cases relate), ranked_tickers (array, "
        "strongest fundamental case first - rank as many as you can), contradictions (array of "
        "strings naming pairs or clusters whose logic conflicts).\n"
        f"Group: {axis} = {label}\nMacro bias: {macro_bias or 'unknown'}\nAs of: {as_of}\n"
        f"Ideas:\n{json.dumps(compact, default=str)[:11000]}"
    )
    return system, user


def group_review(
    kind: str,
    label: str,
    ideas: list[TradeIdea],
    macro_bias: str = "",
    as_of: str = "",
    skip_llm: bool = False,
) -> GroupReview:
    """Read one sector's (or one earnings bucket's) ideas against each other."""
    rows = [name_row(idea) for idea in ideas]
    if not rows:
        return GroupReview(group_kind=kind, group_label=label, as_of=as_of, llm_used=False)
    if skip_llm or not llm_available():
        reason = "--skip-llm" if skip_llm else "no API key"
        return deterministic_review(kind, label, rows, as_of, reason)

    axis = "sector" if kind == "sector" else "earnings window"
    by_ticker = {r["ticker"]: r for r in rows}

    comments: dict[str, str] = {}
    errors: list[str] = []
    for chunk in _chunks(rows, VIEW_CHUNK):
        try:
            payload = chat_json(*_view_prompt(axis, label, chunk))
        except Exception as exc:
            errors.append(str(exc))
            continue
        for item in payload.get("views") or []:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            if ticker in by_ticker and ticker not in comments:
                comments[ticker] = _clip(item.get("comment"), 300)

    try:
        synth = chat_json(*_synthesis_prompt(axis, label, rows, macro_bias, as_of))
    except Exception as exc:
        errors.append(str(exc))
        synth = {}

    if not comments and not synth:
        review = deterministic_review(
            kind, label, rows, as_of, f"LLM failed: {errors[0] if errors else 'no output'}"
        )
        review.error = "; ".join(errors[:2])
        return review

    views = [
        GroupNameView(
            ticker=ticker,
            side=row["side"],
            eg_case=row["eg_case"],
            # The verdict is the first pass's, not the group model's to revise.
            qual_verdict=row["qual_verdict"],
            comment=comments.get(ticker) or "not covered by the group LLM pass",
        )
        for ticker, row in by_ticker.items()
    ]
    ranked: list[str] = []
    for raw in synth.get("ranked_tickers") or []:
        ticker = str(raw).strip().upper()
        if ticker in by_ticker and ticker not in ranked:
            ranked.append(ticker)
    ranked_by_model = len(ranked)
    ranked += [t for t in by_ticker if t not in ranked]
    contradictions = [_clip(c, 300) for c in (synth.get("contradictions") or []) if str(c).strip()]
    return GroupReview(
        group_kind=kind,
        group_label=label,
        as_of=as_of,
        tickers=list(by_ticker),
        llm_used=True,
        covered=len(comments),
        ranked_by_model=ranked_by_model,
        # Counts stay measured; the model supplies prose only.
        summary=group_summary(rows),
        narrative=_clip(synth.get("narrative"), 1400) or _clip(synth.get("summary"), 400),
        views=views,
        ranked_tickers=ranked,
        contradictions=contradictions,
        error="; ".join(errors[:2]),
    )


def render_group_review(review: GroupReview) -> str:
    """Markdown for one group review."""
    axis = "Sector" if review.group_kind == "sector" else "Earnings window"
    llm_line = "yes" if review.llm_used else "no"
    if review.llm_used:
        llm_line += f" — {review.covered}/{len(review.tickers)} names individually reviewed"
    lines = [
        f"# {axis} cross-read - {review.group_label}",
        "",
        f"As of: {review.as_of}  ",
        f"Names: {len(review.tickers)}  ",
        f"LLM: {llm_line}",
        "",
        "> A cross-read of the fundamental cases in this group. Commentary, not a gate:",
        "> no idea is included in or dropped from the book on the strength of this section.",
        "> No price or technical input is used anywhere in this process.",
        "",
        "## Group",
        "",
        review.summary or "n/a",
        "",
        "## Read",
        "",
        review.narrative or "n/a",
        "",
        "## Per name",
        "",
        "| Ticker | Side | EG case | Qualitative | Comment |",
        "|---|---|---|---|---|",
    ]
    for view in review.views:
        comment = (view.comment or "").replace("|", "/")
        lines.append(
            f"| {view.ticker} | {view.side} | {view.eg_case or 'n/a'} | "
            f"{view.qual_verdict} | {comment} |"
        )
    lines += ["", "## Ranking by strength of case", ""]
    if review.llm_used and review.ranked_by_model < len(review.ranked_tickers):
        note = (
            "The model returned no ranking for this group; the order below is screen rank."
            if review.ranked_by_model == 0
            else f"The model ranked the first {review.ranked_by_model} of "
            f"{len(review.ranked_tickers)}; the rest follow in screen-rank order."
        )
        lines += [note, ""]
    lines += [", ".join(review.ranked_tickers) or "n/a", ""]
    if review.contradictions:
        lines += ["## Conflicting logic", ""]
        lines += [f"- {item}" for item in review.contradictions]
        lines.append("")
    if review.error:
        lines += [f"> LLM error: {review.error}", ""]
    return "\n".join(lines)
