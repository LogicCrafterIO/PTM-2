from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ptm.config import data_dir, ideas_dir
from ptm.io import write_json
from ptm.log import log
from ptm.models import Candidate, Side


def long_key(c: Candidate) -> tuple:
    return (0 if c.mcap_ok else 1, -(c.ism_score or 0.0), -(c.eg1 or 0.0))


def short_key(c: Candidate) -> tuple:
    return (0 if c.mcap_ok else 1, -(c.ism_score or 0.0), (c.eg1 or 0.0))


def rank_reason(c: Candidate) -> str:
    if c.pe1 is not None and c.sector_pe1 is not None:
        pe_bit = f"PE {c.pe1:.1f} vs sector {c.sector_pe1:.1f}"
    elif c.pe1 is not None:
        pe_bit = f"PE {c.pe1:.1f}"
    else:
        pe_bit = "PE n/a"
    ism_bit = f"ISM {c.ism_score:+.2f}"
    if c.ism_why:
        ism_bit += f" ({c.ism_why[:80]})"
    mcap_bit = "mcap in band" if c.mcap_ok else (c.mcap_warning or "mcap outside band")
    eg = c.eg_case or "unknown"
    return f"{pe_bit}; {ism_bit}; EG case {eg}; {mcap_bit}"


def ordered_candidates(candidates: list[Candidate]) -> list[Candidate]:
    longs = sorted([c for c in candidates if c.side == Side.LONG], key=long_key)
    shorts = sorted([c for c in candidates if c.side == Side.SHORT], key=short_key)
    return longs + shorts


def ranking_rows(candidates: list[Candidate]) -> list[dict]:
    longs = sorted([c for c in candidates if c.side == Side.LONG], key=long_key)
    shorts = sorted([c for c in candidates if c.side == Side.SHORT], key=short_key)
    rows: list[dict] = []
    for i, cand in enumerate(longs, start=1):
        why = rank_reason(cand)
        rows.append(
            {
                "side": "long",
                "rank": i,
                "of": len(longs),
                "ticker": cand.ticker,
                "name": cand.name,
                "why": f"Long #{i}/{len(longs)}: {why}",
                "ism_score": cand.ism_score,
                "eg_case": cand.eg_case,
                "mcap_ok": cand.mcap_ok,
            }
        )
    for i, cand in enumerate(shorts, start=1):
        why = rank_reason(cand)
        rows.append(
            {
                "side": "short",
                "rank": i,
                "of": len(shorts),
                "ticker": cand.ticker,
                "name": cand.name,
                "why": f"Short #{i}/{len(shorts)}: {why}",
                "ism_score": cand.ism_score,
                "eg_case": cand.eg_case,
                "mcap_ok": cand.mcap_ok,
            }
        )
    return rows


def write_ranking(candidates: list[Candidate], day: str | None = None) -> Path:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = ranking_rows(candidates)
    payload = {"as_of": datetime.now(timezone.utc).isoformat(), "rows": rows}
    json_path = data_dir("curated", "ranking.json")
    write_json(json_path, payload)
    lines = ["# PE candidate ranking", "", f"As of: {payload['as_of']}", ""]
    longs = [r for r in rows if r["side"] == "long"]
    shorts = [r for r in rows if r["side"] == "short"]
    lines.append(f"## Longs ({len(longs)})")
    lines.append("")
    for row in longs:
        lines.append(f"- **{row['ticker']}** — {row['why']}")
    lines += ["", f"## Shorts ({len(shorts)})", ""]
    for row in shorts:
        lines.append(f"- **{row['ticker']}** — {row['why']}")
    md_path = ideas_dir(day, "RANKING.md")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"ranking: {len(longs)} longs / {len(shorts)} shorts → {md_path.name}")
    return md_path
