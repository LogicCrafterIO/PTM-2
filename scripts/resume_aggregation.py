"""Resume the tail of a `ptm weekly` run after the per-idea work is done.

The ideas are already written under ideas/<day>/<Sector>/<bucket>/*.json. This
reloads them and runs the cross-sectional steps that follow: theme cohorts, ISM
alignment, group reviews, the aggregate + window books, momentum, and the audit.
"""
from __future__ import annotations

from ptm.asof import day_slug, is_backdated
from ptm.book import assemble_book
from ptm.books import assemble_books
from ptm.config import data_dir, ideas_dir
from ptm.eval import audit_run, write_audit
from ptm.io import read_json, write_json
from ptm.log import log
from ptm.models import MacroSnapshot, TradeIdea
from ptm.organize import find_idea_files, placements, write_index
from ptm.pipeline import run_group_reviews
from ptm.ranking import cohort_rows, momentum
from ptm.revision_report import write_momentum
from ptm.themes import cohort_momentum, ism_alignment
from ptm.themes import ism_support as theme_ism_support
from ptm.themes import corroboration as theme_corroboration
from ptm.themes import record as record_themes


def main() -> None:
    day = day_slug()
    folder = ideas_dir(day)
    paths = find_idea_files(folder)
    ideas: list[TradeIdea] = []
    for path in paths:
        payload = read_json(path)
        if isinstance(payload, dict) and payload.get("candidate"):
            ideas.append(TradeIdea.model_validate(payload))
    log(f"resume: loaded {len(ideas)} ideas from {folder}")

    snap = MacroSnapshot.model_validate(read_json(data_dir("curated", "macro_snapshot.json")))

    # Theme cohorts + ISM alignment (cross-sectional, deterministic).
    cohorts = cohort_momentum(cohort_rows(ideas))
    ism_raw = read_json(data_dir("curated", "ism.json")) if data_dir("curated", "ism.json").exists() else {}
    ism_themes = ism_alignment(ism_raw if isinstance(ism_raw, dict) else {})
    for idea in ideas:
        themes = list((idea.qual.themes if idea.qual else None) or [])
        drift = idea.extra.get("drift") or {}
        idea.extra["theme_corroboration"] = theme_corroboration(
            themes, int(drift.get("direction") or 0), cohorts
        )
        idea.extra["ism_support"] = theme_ism_support(themes, ism_themes)
        idea.extra["revision_momentum"] = momentum(idea)
    write_json(data_dir("curated", "theme_ism_alignment.json"), ism_themes)
    write_json(data_dir("curated", "theme_cohorts.json"), cohorts)
    log(f"resume: themes done ({len(cohorts)} cohorts)")

    # Group reviews (LLM cross-read).
    run_group_reviews(ideas, snap, day=day, skip_llm=False)
    write_json(data_dir("curated", "ideas.json"), [i.model_dump() for i in ideas])

    rows = placements(ideas)
    notes = []
    if is_backdated():
        notes.append(f"Backdated run: every date below is measured from {day}, not from today.")
    write_index(rows, day=day, extra_notes=notes)

    book = assemble_book(ideas, snap.bias)
    log(f"resume: book {book.narrative}")
    write_momentum(ideas, {i.candidate.ticker for i in book.ideas}, day=day)
    assemble_books(ideas, snap.bias, day=day)
    record_themes(
        day,
        {
            i.candidate.ticker: [
                {"theme": str(t).rsplit(" (", 1)[0], "mentions": int(str(t).rsplit("(", 1)[1].rstrip(")"))}
                for t in (i.qual.themes or [])
                if "(" in str(t)
            ]
            for i in ideas
            if i.qual is not None and i.qual.themes
        },
    )

    audit = audit_run()
    report = write_audit(audit)
    log(f"resume: audit {len(audit.findings)} findings -> {report}")
    log("resume: done")


if __name__ == "__main__":
    main()
