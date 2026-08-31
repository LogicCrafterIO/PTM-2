"""Rescore every idea from its existing deep-dive cache — no LLM, no re-dive.

Recovers from a scoring-rule change (category-weight demotion + absent-category
renormalization) without paying for 197 new dives: for each idea we recompute
the evidence score from the dive's own synthesis-scored drivers, re-resolve the
support verdict with the score-first rule, re-apply the deterministic gates,
re-render the dive report and idea file with the corrected scorecard, then
rebuild the books, momentum map and group reviews.

The deep dives themselves are untouched — their text, drivers, debates and
synthesis stance are exactly what the last run produced. Only the numbers
derived from them change, and every flip is recorded on the idea
(``extra.rescored``) so the change stays auditable.
"""

from __future__ import annotations

from ptm import pipeline as pl
from ptm.log import log
from ptm.config import data_dir, ideas_dir
from ptm.io import read_json, write_json
from ptm.models import IdeaState, MacroSnapshot, Side, TradeIdea


def _flip_why(why: str | None, stance: str, s: float) -> str:
    """Re-stamp the '[dive: stance | S=+x.xx]' prefix on the stored verdict why."""
    body = (why or "").split("] ", 1)[-1]
    return f"[dive: {stance or 'unclear'} | S={s:+.2f}] {body}"


def rescore_ideas(ideas: list[TradeIdea], day: str) -> dict:
    """Recompute scores/supports/gates/states for every idea with a dive cache."""
    from ptm.deepsearch.models import DeepResult
    from ptm.deepsearch.render import render_idea_markdown, render_markdown
    from ptm.deepsearch.verdict import _resolved_supports, aggregate_scores, driver_rows
    from ptm.gates import apply_process_gates
    from ptm.organize import idea_paths

    changes = {"rescored": 0, "support_flips": 0, "gate_changes": 0, "no_cache": 0}
    flips: list[str] = []
    for idea in ideas:
        cand = idea.candidate
        path = data_dir("raw", "deepsearch", "runs", f"{cand.ticker}.json")
        if not path.exists() or idea.qual is None:
            changes["no_cache"] += 1
            continue
        result = DeepResult.model_validate(read_json(path))
        rows = driver_rows(result.thesis)
        if not rows:
            changes["no_cache"] += 1
            continue
        agg = aggregate_scores(rows)
        if agg["s"] is None:
            changes["no_cache"] += 1
            continue
        old_support = idea.qual.supports_outlier
        sup, _flags = _resolved_supports(agg["s"], result.thesis.stance, Side(cand.side))
        if sup is None:
            # Inside the band the stance label decides, exactly as at run time.
            sup = old_support
        idea.qual.supports_outlier = sup
        idea.qual.score_s = agg["s"]
        idea.qual.score_long = agg["long"]
        idea.qual.score_short = agg["short"]
        for cat in ("valuation", "fundamentals", "catalysts", "competitive", "risk"):
            setattr(idea.qual, f"score_{cat}", agg[cat])
        idea.qual.driver_scores = rows
        idea.qual.why = _flip_why(idea.qual.why, result.thesis.stance, agg["s"])
        idea.state = (
            IdeaState.QUAL_PASS if sup is True else (IdeaState.QUAL_FAIL if sup is False else idea.state)
        )
        if old_support != sup:
            changes["support_flips"] += 1
            flips.append(f"{cand.ticker} {str(old_support)} -> {sup}")
        old_gates = list(idea.extra.get("gates") or [])
        new_gates = apply_process_gates(idea)
        if old_gates != new_gates:
            changes["gate_changes"] += 1
        idea.extra["gates"] = new_gates
        idea.extra["rescored"] = {
            "why": "renormalized absent categories + demoted valuation weight (see scorecard note)",
            "old_support": old_support,
            "new_support": sup,
        }
        # Re-render the dive report: its scorecard carries the new numbers.
        deep_md = render_markdown(result)
        report_path = ideas_dir("deepdive", cand.ticker) / "REPORT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(deep_md, encoding="utf-8")
        # Re-render the idea file with the corrected header chip.
        idea.template_markdown = render_idea_markdown(
            cand,
            idea.qual,
            idea.catalysts,
            idea.earnings,
            idea.extra.get("expectations"),
            deep_md,
            idea.extra.get("deepdive"),
        )
        if idea.state == IdeaState.QUAL_PASS:
            idea.state = IdeaState.TEMPLATED  # matches the pipeline's post-render state
        md_path, json_path = idea_paths(idea, day=day)
        md_path.write_text(idea.template_markdown or "", encoding="utf-8")
        write_json(json_path, idea.model_dump())
        changes["rescored"] += 1
    changes["flips"] = flips
    log(
        f"rescore: {changes['rescored']} ideas re-scored, {changes['support_flips']} support "
        f"flips, {changes['gate_changes']} gate changes, {changes['no_cache']} without usable cache"
    )
    return changes


def load_ideas() -> list[TradeIdea]:
    return [TradeIdea.model_validate(r) for r in read_json(data_dir("curated", "ideas.json"))]


def rebuild(day: str, review_llm: bool = False, ideas: list[TradeIdea] | None = None) -> dict:
    """Rebuild the derived artifacts from the (re-resolved) idea records."""
    # Default to the curated records; callers that just re-resolved pass the
    # mutated list through so the book never sees stale verdicts.
    if ideas is None:
        ideas = load_ideas()
    snap = MacroSnapshot.model_validate(read_json(data_dir("curated", "macro_snapshot.json")))
    # Group reviews consume the CORRECTED first-pass verdicts; without LLM they
    # are deterministic stubs, with LLM a cheap cross-read (25 small calls).
    reviews = pl.run_group_reviews(ideas, snap, day=day, skip_llm=not review_llm)
    write_json(data_dir("curated", "ideas.json"), [i.model_dump() for i in ideas])
    rows = pl.placements(ideas)
    pl.write_index(rows, day=day)
    book = pl.assemble_book(ideas, snap.bias)
    log(f"rescore: book rebuilt -> {book.narrative}")
    from ptm.revision_report import write_momentum
    write_momentum(ideas, {i.candidate.ticker for i in book.ideas}, day=day)
    from ptm.books import assemble_books
    assemble_books(ideas, snap.bias, day=day)
    return {"reviews": len(reviews), "book_names": len(book.ideas)}


def _latest_day() -> str:
    days = sorted(p.name for p in ideas_dir().glob("2026-*") if p.is_dir())
    if not days:
        raise RuntimeError("no idea day folders found")
    return days[-1]


def apply_rescore(review_llm: bool = False, day: str | None = None) -> dict:
    """Entry point: re-resolve every verdict from the new scoring, rebuild everything."""
    from ptm.asof import set_as_of

    day = day or _latest_day()
    set_as_of(day)  # keep earnings/bucket pins consistent with the idea files
    ideas = load_ideas()
    changes = rescore_ideas(ideas, day=day)
    out = {k: v for k, v in changes.items() if k != "flips"}
    out["flip_tickers"] = changes["flips"]
    out.update(rebuild(day, review_llm=review_llm, ideas=ideas))  # pass the mutated list through
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review-llm", action="store_true", help="re-run group reviews with the LLM")
    ap.add_argument("--day", default="", help="run day the idea files live under")
    args = ap.parse_args()
    result = apply_rescore(review_llm=args.review_llm, day=args.day or None)
    print({k: v for k, v in result.items() if k != "flip_tickers"})
    print("support flips:", result.get("flip_tickers"))