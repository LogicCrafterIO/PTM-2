"""Filing ideas into ideas/<day>/<Sector>/<earnings-bucket>/.

Two axes the desk actually sorts on: what the name does, and how soon it
reports. Windows are **calendar days** from the run date, the same units as the
PTM catalyst window (30-90 calendar days, i.e. the process's 20-60 trading
days), so a name in the 31-60d or 61-90d bucket can actually satisfy the gate.

Every idea gets a date: when none is published, ptm/earnings.py projects the
next report from the company's own filing cadence and states so in full. There
is no "no earnings date" or "already reported" folder as a result.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ptm.asof import as_of_date, day_slug
from ptm.config import ideas_dir, toml_settings
from ptm.earnings import resolve as resolve_earnings
from ptm.earnings import sentence as earnings_sentence
from ptm.models import EarningsEstimate, TradeIdea

UNCLASSIFIED = "Unclassified-Sector"
# Quarterly reporters land inside 90 calendar days once a date is projected, so this
# should stay empty; it exists so an annual-only filer is never dropped.
BEYOND = "beyond-90d"

ROOT_DOCS = {"RANKING.md", "AUDIT.md", "INDEX.md", "EARNINGS_REVIEW.md"}


def bucket_edges() -> list[int]:
    cfg = toml_settings().get("earnings_buckets") or {}
    edges = [int(x) for x in (cfg.get("edges") or [30, 60, 90])]
    return sorted(set(edges))


def _bucket_name(low: int, high: int) -> str:
    return f"{low:02d}-{high:02d}d"


def bucket_names() -> list[str]:
    """The three primary buckets, in order."""
    names = []
    low = 0
    for edge in bucket_edges():
        names.append(_bucket_name(low, edge))
        low = edge + 1
    return names


def sector_slug(sector: str | None) -> str:
    """Filesystem-safe sector folder name. 'Health Care' -> 'Health-Care'."""
    text = str(sector or "").strip()
    if not text:
        return UNCLASSIFIED
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text or UNCLASSIFIED


def bucket_for_days(days: int | None) -> str:
    """Folder for a number of calendar days to the next report."""
    if days is None:
        return bucket_names()[-1]
    days = max(int(days), 0)
    low = 0
    for edge in bucket_edges():
        if days <= edge:
            return _bucket_name(low, edge)
        low = edge + 1
    return BEYOND


def earnings_for(idea: TradeIdea, ref: date | None = None) -> EarningsEstimate:
    """The estimate attached to an idea, resolving it once if absent."""
    if idea.earnings is not None:
        return idea.earnings
    raw = idea.catalysts.earnings_date if idea.catalysts else None
    idea.earnings = resolve_earnings(idea.candidate.ticker, raw, ref=ref or as_of_date())
    return idea.earnings


def idea_folder(idea: TradeIdea, day: str | None = None, ref: date | None = None) -> Path:
    """ideas/<day>/<Sector>/<bucket>/ for one idea, created on demand."""
    estimate = earnings_for(idea, ref=ref)
    folder = ideas_dir(
        day or day_slug(),
        sector_slug(idea.candidate.sector),
        bucket_for_days(estimate.days_to_earnings),
    )
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def idea_paths(idea: TradeIdea, day: str | None = None, ref: date | None = None) -> tuple[Path, Path]:
    """(markdown path, json path) for an idea, under its sector/bucket folder."""
    folder = idea_folder(idea, day=day, ref=ref)
    stem = f"{idea.candidate.side.value}_{idea.candidate.ticker}"
    return folder / f"{stem}.md", folder / f"{stem}.json"


def placement(idea: TradeIdea, ref: date | None = None) -> dict:
    """Where an idea landed, plus the reasoning that put it there."""
    cand = idea.candidate
    estimate = earnings_for(idea, ref=ref)
    bucket = bucket_for_days(estimate.days_to_earnings)
    return {
        "ticker": cand.ticker,
        "side": cand.side.value,
        "sector": cand.sector or "",
        "sector_folder": sector_slug(cand.sector),
        "bucket": bucket,
        "earnings_date": estimate.date,
        "earnings_estimated": estimate.estimated,
        "days_to_earnings": estimate.days_to_earnings,
        "earnings_basis": estimate.basis,
        "earnings_note": earnings_sentence(estimate, bucket),
        "state": idea.state.value,
        "gates": list(idea.extra.get("gates") or []),
    }


def placements(ideas: list[TradeIdea], ref: date | None = None) -> list[dict]:
    return [placement(idea, ref=ref) for idea in ideas]


def group_by_sector(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["sector_folder"], []).append(row)
    return dict(sorted(out.items()))


def group_by_bucket(rows: list[dict]) -> dict[str, list[dict]]:
    order = bucket_names() + [BEYOND]
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["bucket"], []).append(row)
    return {name: out[name] for name in order if name in out}


def find_idea_files(day_folder: Path) -> list[Path]:
    """Every idea JSON under a day folder, at any depth."""
    if not day_folder or not day_folder.exists():
        return []
    return sorted(p for p in day_folder.rglob("*.json") if p.stem not in {"INDEX", "AUDIT"})


def find_idea_markdown(day_folder: Path, side: str, ticker: str) -> Path | None:
    """Locate one idea's markdown wherever it was filed."""
    if not day_folder or not day_folder.exists():
        return None
    for path in day_folder.rglob(f"{side}_{ticker}.md"):
        return path
    return None


def write_index(rows: list[dict], day: str | None = None, extra_notes: list[str] | None = None) -> Path:
    """A map of the tree at the day root, so the folders are navigable."""
    day = day or day_slug()
    by_sector = group_by_sector(rows)
    by_bucket = group_by_bucket(rows)
    estimated = [r for r in rows if r.get("earnings_estimated")]
    lines = [
        "# Idea index",
        "",
        f"As of: {day}",
        f"Ideas: {len(rows)} across {len(by_sector)} sectors",
        "",
        "Windows are **calendar days** to the next report, measured from the run date.",
        "",
    ]
    for note in extra_notes or []:
        lines.append(f"> {note}")
    if extra_notes:
        lines.append("")
    if estimated:
        lines += [
            f"> {len(estimated)} of {len(rows)} ideas have no published future earnings date; "
            "their next report is projected from filing cadence and marked *(est.)* below.",
            "",
        ]
    lines += ["## By sector", ""]
    for sector, items in by_sector.items():
        lines.append(f"### {sector} ({len(items)})")
        lines.append("")
        for row in sorted(items, key=lambda r: (r["bucket"], r["ticker"])):
            days = row["days_to_earnings"]
            days_txt = "n/a" if days is None else f"{days}d"
            mark = " *(est.)*" if row.get("earnings_estimated") else ""
            lines.append(
                f"- `{row['bucket']}/` **{row['side']}_{row['ticker']}** — "
                f"earnings {row['earnings_date'] or 'unknown'}{mark} ({days_txt}), state {row['state']}"
            )
            if row.get("earnings_estimated") and row.get("earnings_basis"):
                lines.append(f"  - {row['earnings_basis']}")
        lines.append("")
    lines += ["## By earnings window", ""]
    for bucket, items in by_bucket.items():
        tickers = ", ".join(f"{r['side']}_{r['ticker']}" for r in sorted(items, key=lambda r: r["ticker"]))
        lines.append(f"- **{bucket}** ({len(items)}): {tickers}")
    lines.append("")
    path = ideas_dir(day, "INDEX.md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
