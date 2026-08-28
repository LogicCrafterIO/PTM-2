"""One book per earnings window, so momentum is held against a dated catalyst.

A single book mixed names reporting next week with names reporting in eleven
weeks, ranked them on the same number, and let the far-dated ones win because
time never entered the comparison. Splitting by window makes the horizon explicit
instead: each book competes only against names whose catalyst lands in the same
period, so a five-day idea is measured against other five-day ideas.

The windows match the folder buckets in ptm/organize.py and the same calendar-day
units as the catalyst gate, so a name's bucket and its eligibility agree.

**These books are not equally fillable, and that is the point of separating
them.** On the first run after the split, the 00-30d window held 1 eligible long
and no shorts at all, and 31-60d held 5 longs and no shorts - every near-dated
short had been gated on the qualitative verdict or the filings veto. A near-term
book that comes back with one name is telling you the universe has one name worth
holding into a print that soon; a combined book hid that by topping up from
eleven weeks out.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ptm.book import assemble_book
from ptm.config import data_dir, ideas_dir, toml_settings
from ptm.io import write_json
from ptm.log import log
from ptm.models import Bias, BookProposal, Side, TradeIdea

# Same edges as the idea folders and the catalyst gate, in calendar days.
WINDOWS: tuple[tuple[str, int, int], ...] = (
    ("00-30d", 0, 30),
    ("31-60d", 31, 60),
    ("61-90d", 61, 90),
)


def window_of(idea: TradeIdea) -> str | None:
    """Which earnings window this idea's catalyst falls in, or None."""
    days = idea.earnings.days_to_earnings if idea.earnings else None
    if days is None:
        return None
    for label, low, high in WINDOWS:
        if low <= days <= high:
            return label
    return None


def _split(ideas: list[TradeIdea]) -> dict[str, list[TradeIdea]]:
    out: dict[str, list[TradeIdea]] = {label: [] for label, _, _ in WINDOWS}
    for idea in ideas:
        label = window_of(idea)
        if label:
            out[label].append(idea)
    return out


def assemble_books(ideas: list[TradeIdea], bias: Bias, day: str | None = None) -> dict[str, BookProposal]:
    """A separate book per earnings window, each written to its own file.

    Every book runs the full selection: sector cap, size bands, beta rebalance
    and the same ranking. Nothing is relaxed to fill a thin window - a book that
    cannot fill comes back short with a breach saying why, which is the honest
    answer when only one name qualifies.
    """
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    groups = _split(ideas)
    books: dict[str, BookProposal] = {}
    summary: list[dict] = []
    for label, low, high in WINDOWS:
        group = groups[label]
        book = assemble_book(group, bias, persist=False)
        books[label] = book
        longs = sum(1 for i in book.ideas if i.candidate.side == Side.LONG)
        shorts = len(book.ideas) - longs
        write_json(data_dir("curated", f"book_{label}.json"), book.model_dump())
        summary.append(
            {
                "window": label,
                "days": [low, high],
                "candidates": len(group),
                "selected": len(book.ideas),
                "longs": longs,
                "shorts": shorts,
                "portfolio_beta": book.portfolio_beta,
                "net_exposure": book.net_exposure,
                "breaches": list(book.limit_breaches or []),
            }
        )
        log(
            f"book {label}: {longs} longs / {shorts} shorts from {len(group)} candidates"
            + (f"; beta {book.portfolio_beta:+.3f}" if book.portfolio_beta is not None else "")
        )
    write_json(
        data_dir("curated", "books_by_window.json"),
        {"as_of": datetime.now(timezone.utc).isoformat(), "windows": summary},
    )
    _write_markdown(books, summary, day)
    return books


def _rows(book: BookProposal) -> list[str]:
    if not book.ideas:
        return ["_no name qualified in this window_", ""]
    out = [
        "| Side | Ticker | Revision | Score | Days | Durability | Beta | Sector |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for idea in book.ideas:
        cand = idea.candidate
        mom = idea.extra.get("revision_momentum") or {}
        days = idea.earnings.days_to_earnings if idea.earnings else None
        beta = idea.prm.beta if idea.prm and idea.prm.beta is not None else None
        out.append(
            f"| {cand.side.value} | {cand.ticker} | "
            f"{'—' if mom.get('raw_edge_pct') is None else format(mom['raw_edge_pct'], '+.1f')} | "
            f"{'—' if mom.get('edge_score') is None else format(mom['edge_score'], '+.1f')} | "
            f"{'—' if days is None else days} | {mom.get('durability') or '—'} | "
            f"{'—' if beta is None else format(beta, '+.2f')} | {(cand.sector or '')[:26]} |"
        )
    return out + [""]


def _write_markdown(books: dict[str, BookProposal], summary: list[dict], day: str) -> Path:
    lines = [
        "# Books by earnings window",
        "",
        f"As of {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "One book per earnings window, so revision momentum is held against a dated catalyst "
        "rather than averaged across horizons. A single combined book let names reporting in "
        "eleven weeks outrank names reporting next week, because time never entered the "
        "comparison.",
        "",
        "**Revision** is the measured distance analyst estimates have moved; **Score** is the "
        "log-compressed value the ranking uses. **Days** is calendar days to the projected "
        "report — every date is projected from filing cadence, since EDGAR publishes no forward "
        "calendar.",
        "",
        "| Window | Candidates | Selected | Longs | Shorts | Beta |",
        "|---|---|---|---|---|---|",
    ]
    for row in summary:
        beta = row["portfolio_beta"]
        lines.append(
            f"| {row['window']} | {row['candidates']} | {row['selected']} | {row['longs']} | "
            f"{row['shorts']} | {'—' if beta is None else format(beta, '+.3f')} |"
        )
    lines.append("")
    for label, low, high in WINDOWS:
        book = books[label]
        row = next(r for r in summary if r["window"] == label)
        lines += [f"## {label} — reporting in {low}-{high} days", ""]
        lines += _rows(book)
        if row["breaches"]:
            lines += ["**Constraints hit:**", ""]
            lines += [f"* {b}" for b in row["breaches"]]
            lines.append("")
    lines += [
        "## Why a window can come back thin",
        "",
        "Nothing is relaxed to fill a book. A window that returns one name is saying the "
        "universe holds one name worth carrying into a print that soon — the near-dated shorts "
        "on the first run after this split were all gated on the qualitative verdict or the "
        "filings veto, so the two near books were long-only. A combined book hid exactly that by "
        "topping up from eleven weeks out.",
        "",
    ]
    path = ideas_dir(day, "BOOKS_BY_WINDOW.md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"books: wrote {path.name}")
    return path
