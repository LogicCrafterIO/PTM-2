"""The ranked momentum report: which way estimates are moving, and how hard.

Ranked on **revision momentum** - the direction analyst estimates are already
travelling, in the direction each trade needs - not on a mispricing. Mispricings
are close to unidentifiable from filings, and two attempts to find them are
recorded in ptm/drift.py as things not to rebuild.

The magnitude is measured: the distance estimates have already moved. It is
scaled by how much of the run looks left (durability), whether the other names
exposed to the same theme are moving the same way (theme cohort), and whether
ISM respondents in the relevant industries are seeing growing orders. The
filings do not generate the signal - they can veto a name whose own reported
numbers contradict the revision being followed.

Nothing here reads a price, a return or a chart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ptm.config import data_dir, ideas_dir
from ptm.io import write_json
from ptm.log import log
from ptm.models import Side, TradeIdea
from ptm.ranking import conviction, momentum, theme_score


def _row(idea: TradeIdea) -> dict:
    cand, qual = idea.candidate, idea.qual
    detail = momentum(idea)
    gap = detail.get("edge_pct")
    implied = (idea.extra.get("expectations") or {}).get("implied") or {}
    return {
        "ticker": cand.ticker,
        "name": cand.name,
        "side": cand.side.value,
        "sector": cand.sector,
        "verdict": None if qual is None else qual.supports_outlier,
        "gated": bool(idea.extra.get("gates")),
        "gates": list(idea.extra.get("gates") or []),
        # The number this file exists to rank on.
        "edge_pct": gap,
        # What the book actually ranks on: the log-compressed score. Removing
        # the winsor cap stopped the ties it created, and immediately let one
        # genuine +347% revision out-score the rest of the book ten to one.
        "gap_weighted": detail.get("edge_score"),
        "edge_score": detail.get("edge_score"),
        "veto": detail.get("veto"),
        "support": detail.get("support"),
        "filing_direction": detail.get("filing_direction"),
        "consensus_direction": detail.get("consensus_direction"),
        "revision_magnitude_pct": detail.get("magnitude_pct"),
        "why": detail.get("why"),
        "direction_basis": None if qual is None else qual.direction_basis,
        "themes": [] if qual is None else list(qual.themes or []),
        "theme_score": theme_score(idea),
        "market_expectation": None if qual is None else qual.market_expectation,
        "deviation": None if qual is None else qual.deviation,
        "priced_in": None if qual is None else qual.priced_in,
        "conviction": conviction(idea),
        # Context, not a ranking input.
        "consensus_eps1": cand.eps1,
        "consensus_eg1": cand.eg1,
        "pe1": cand.pe1,
        "sector_pe1": cand.sector_pe1,
        "relative_peg": cand.relative_peg,
        "implied_move_pct": implied.get("implied_move_pct") if implied.get("available") else None,
        "earnings_date": idea.earnings.date if idea.earnings else None,
    }


def _support(row: dict) -> str:
    """How the filings relate to the revision being followed."""
    if row.get("veto"):
        return "**VETOED**"
    if row.get("support"):
        return "filings agree"
    return "filings silent"


def _sort_key(row: dict) -> tuple:
    """Best gap first; an absent gap sorts last rather than as a zero."""
    return (row["gap_weighted"] is None, -(row["gap_weighted"] or 0.0))


def momentum_rows(ideas: list[TradeIdea]) -> list[dict]:
    """Every idea, ranked by the expectation gap within its side.

    Ranks are numbered among the *eligible* names only. Numbering across gated
    ones too made the visible table read "22, 26, 25" - the ranks were right but
    unreadable, and the gated names are listed separately anyway.
    """
    rows = [_row(i) for i in ideas]
    for side in ("long", "short"):
        eligible = sorted(
            (r for r in rows if r["side"] == side and not r["gated"] and r["verdict"] is True),
            key=_sort_key,
        )
        for n, row in enumerate(eligible, start=1):
            row["rank_in_side"] = n
            row["of_side"] = len(eligible)
    return rows


def _table(rows: list[dict]) -> list[str]:
    if not rows:
        return ["_none_", ""]
    out = [
        "| # | Ticker | Revision | Score | Estimates | Filings | Check | Themes | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=_sort_key):
        gap = r["edge_pct"]
        gap_text = "—" if gap is None else f"**{gap:+.1f}%**"
        move = r["implied_move_pct"]
        move_text = "—" if move is None else f"{move:.0f}%"
        status = "gated" if r["gated"] else ("in book" if r.get("in_book") else "eligible")
        themes = ", ".join(str(t).rsplit(" (", 1)[0] for t in (r.get("themes") or [])[:2]) or "—"
        out.append(
            f"| {r.get('rank_in_side', '—')} | {r['ticker']} | {gap_text} | "
            f"{'—' if r.get('edge_score') is None else format(r['edge_score'], '+.1f')} | "
            f"{r.get('consensus_direction') or '—'} | {r.get('filing_direction') or '—'} | "
            f"{_support(r)} | "
            f"{themes.replace('|', '/')} | {status} |"
        )
    return out + [""]


def render(rows: list[dict], book_tickers: set[str] | None = None) -> str:
    book_tickers = book_tickers or set()
    for r in rows:
        r["in_book"] = r["ticker"] in book_tickers
    live = [r for r in rows if not r["gated"] and r["verdict"] is True]
    longs = [r for r in live if r["side"] == "long"]
    shorts = [r for r in live if r["side"] == "short"]
    sized = [r for r in live if r["edge_pct"] is not None]

    lines = [
        "# Revision momentum: which way estimates are moving, and how hard",
        "",
        f"As of {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "Ranked by the **expectation gap**: how far analysts have already revised their "
        "estimates, weighted by whether this company's own filings agree with the direction "
        "they moved. Signed so a positive number always means *wrong in the direction this "
        "trade needs*.",
        "",
        f"{len(sized)} of {len(live)} eligible ideas carry measurable momentum.",
        "",
        "## Read this first",
        "",
        "* **Revision** is the true distance estimates have moved; **Score** is what the book "
        "ranks on, a log transform of it. Ordering is identical, but a +347% revision no longer "
        "out-scores a +35% one ten to one. A ±30% cap used to sit here and was worse: it created "
        "ties at the top AND laundered two arithmetic artefacts into plausible numbers.",
        "* **The magnitude is measured, not estimated.** It is the distance consensus has "
        "already travelled - what a correction would have to give back. An earlier version "
        "asked a model to estimate an EPS surprise instead; the figures clustered on round "
        "numbers and every name came back \"medium\" confidence, because backing out a "
        "consensus-implied growth rate is arithmetic a mid-sized model cannot do.",
        "* **The direction comes from the filings.** That is a classification, which a model "
        "does reliably. The two are combined by whether they agree.",
        "* **\"analysts wrong\" is the case worth reading.** Estimates being cut on a company "
        "whose own filings point up - or raised on one pointing down. Both halves are "
        "checkable, and the filings are the primary source.",
        "* **\"priced\" means the thesis is probably right and probably known.** Discounted "
        "rather than dropped: being right slightly early still beats being wrong.",
        "* **An earnings gap is not a price gap**, and this is relative to consensus rather "
        "than to fair value.",
        "* Themes come from each company's own filings, not from news - see ptm/themes.py. "
        "They are context and a tiebreak, never a thesis.",
        "",
        f"## Longs — analyst estimates rising ({len(longs)})",
        "",
        *_table(longs),
        f"## Shorts — analyst estimates falling ({len(shorts)})",
        "",
        *_table(shorts),
    ]
    blocked = [r for r in rows if r["gated"] or r["verdict"] is not True]
    if blocked:
        lines += [
            f"## Not eligible ({len(blocked)})",
            "",
            "Carried here so a name's absence from the book is explainable rather than silent.",
            "",
            "| Ticker | Side | Gap | Why not |",
            "|---|---|---|---|",
        ]
        for r in sorted(blocked, key=lambda x: x["ticker"]):
            gap = r["edge_pct"]
            reason = "; ".join(r["gates"]) or ("verdict denied the outlier" if r["verdict"] is False else "no verdict")
            lines.append(
                f"| {r['ticker']} | {r['side']} | {'—' if gap is None else f'{gap:+.1f}%'} | "
                f"{reason.replace('|', '/')[:90]} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_momentum(
    ideas: list[TradeIdea], book_tickers: set[str] | None = None, day: str | None = None
) -> Path:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = momentum_rows(ideas)
    write_json(
        data_dir("curated", "momentum.json"),
        {"as_of": datetime.now(timezone.utc).isoformat(), "rows": rows},
    )
    path = ideas_dir(day, "MOMENTUM.md")
    path.write_text(render(rows, book_tickers), encoding="utf-8")
    sized = sum(1 for r in rows if r["edge_pct"] is not None)
    log(f"momentum: {sized}/{len(rows)} ideas carry a sized expectation gap → {path.name}")
    return path


def gap_line(qual, candidate, expectations: dict | None = None) -> str:
    """The revision-momentum line for one idea's markdown.

    Delegates to ptm/drift.py so the number on the page is the same one the
    ranking used, computed the same way.
    """
    from ptm.drift import consensus_drift, momentum_edge, summary_line

    drift = consensus_drift(expectations)
    payload = momentum_edge(drift, qual, candidate.side == Side.LONG)
    line = summary_line(payload)
    basis = (getattr(qual, "direction_basis", "") or "").strip() if qual else ""
    if basis:
        line += f" Filings read as {payload.get('filing_direction')} because: {basis}"
    return line
