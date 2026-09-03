"""One-time migration: dedupe theme-map memberships and re-derive the ranking.

Option A applied to an existing run WITHOUT re-sweeping: each ticker keeps only
its largest theme, so no name is ranked twice and no name appears twice on one
leaderboard. The per-group LLM judgements from the existing sweep are reused —
membership sets only shrink under the dedup, so every surviving member of a
theme was already ranked inside that very theme. What changes:

  - the map: memberships deduplicated (a theme all of whose members carry a
    bigger label elsewhere simply empties out — the sub-3 label-spam themes
    mostly die here);
  - radar + quant: rebuilt deterministically over the deduped map (no LLM);
  - groups: each surviving theme keeps its sweep's rows, filtered to members
    still in the theme, ordered by the sweep's own rank order, with the factual
    table cells re-rendered from the DEDUPED quant table — the model's prose is
    kept verbatim, the measured columns are always computed, never stored;
  - the cross-industry final is the one fresh LLM call, over the new winners.

Groups carry `derived: true` and say in their headline note how many members
moved to their primary industry: the sweep's prose was written under the
pre-dedup groupings.

    python scripts/dedupe_setups.py            # derives from the newest setups JSON
    python scripts/dedupe_setups.py --old data/setups/setups_2026-09-02.json
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from ptm.log import log

_NOTE = "membership deduplicated since this ranking was written"


def _dedupe_map() -> dict:
    from ptm_simple import simple_dir
    from ptm_simple.wiki_themes import dedupe_memberships

    path = simple_dir("theme_map_wiki.json")
    m = json.loads(path.read_text(encoding="utf-8"))
    themes = dedupe_memberships(m["themes"])
    rev: dict[str, list[str]] = {}
    for t in themes:
        for mem in t["members"]:
            rev.setdefault(mem, []).append(t["theme"])
    out = {
        **m,
        "built_at": time.time(),
        "theme_count": len(themes),
        "ticker_count": len(rev),
        "membership": "largest-theme-per-ticker (deduped)",
        "themes": themes,
        "ticker_themes": {k: sorted(v) for k, v in sorted(rev.items())},
    }
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log(f"dedupe: {m['theme_count']} -> {len(themes)} themes, "
        f"{sum(1 for v in rev.values() if len(v) > 1)} multi-membership tickers -> {path.name}")
    return out


def _radar_and_quant(ref: date) -> tuple[dict, dict]:
    """Deterministic front half over the deduped map; no LLM anywhere."""
    from ptm_simple.quant import build_quant
    from ptm_simple.radar import _fundamentals, run_radar, write_radar
    from ptm_simple.run import load_theme_map

    theme_map = load_theme_map("wiki")
    fund = _fundamentals()
    rows = run_radar(theme_map, ref)
    write_radar(rows, ref, theme_map)
    non_cold = [r for r in rows if r["status"] != "COLD"]
    members = {r["theme"]: r["members"] for r in rows}
    build_quant(ref, non_cold, members)
    return {r["theme"]: r for r in rows if r["status"] != "COLD"}, members


def _pick_from_row(row: dict, side: str) -> dict:
    """Promote a ranking row to a side's headline pick when the sweep's own
    declared pick moved to its primary industry: the row carries the model's
    case fields, so nothing is invented."""
    return {
        "ticker": row["ticker"],
        "side": side,
        "thesis": row.get("ranked_on") or "",
        "catalyst": row.get("catalyst") or "",
        "setup": row.get("setup") or "",
        "risk": row.get("risk") or "",
        "conviction": row.get("conviction") or "medium",
        "derived_pick": True,
    }


def _derive_group(theme_row: dict, old_group: dict, quant_by_ticker: dict, ref: date) -> dict | None:
    """Rebuild one group from its sweep's rows, filtered to surviving members."""
    from ptm_setups.inputs import member_packet
    from ptm_setups.rank import _row

    members = {m["ticker"]: m for m in theme_row.get("members") or []}
    old_rows = sorted((old_group.get("ranking") or []), key=lambda r: r.get("rank") or 99)
    items: list[tuple[dict, dict]] = []
    lost: list[str] = []
    for old in old_rows:
        ticker = old.get("ticker") or ""
        if ticker not in members:
            lost.append(ticker)
            continue
        item = {k: old.get(k) for k in
                ("side", "label", "conviction", "ranked_on", "guidance_valuation",
                 "catalyst", "setup", "risk")}
        items.append((old, item))
    if not items:
        return None

    ranking = []
    for i, (old, item) in enumerate(items, 1):
        ticker = old["ticker"]
        packet = member_packet(ticker, members[ticker], quant_by_ticker.get(ticker) or {}, ref)
        ranking.append(_row(packet, item, i))
    out = {
        "theme": theme_row["theme"],
        "status": theme_row.get("status"),
        "lean": theme_row.get("lean"),
        "breadth": theme_row.get("breadth"),
        "thesis": old_group.get("thesis", ""),
        "members_ranked": len(ranking),
        "members_skipped": [t for t in (old_group.get("members_skipped") or []) if t in members],
        "headline": old_group.get("headline", ""),
        "tactical": old_group.get("tactical", ""),
        "short_first": (theme_row.get("breadth") or 0.0) <= 0.2,
        "best_long": None,
        "best_short": None,
        "ranking": ranking,
        "llm_used": bool(old_group.get("llm_used")),
        "model": old_group.get("model", ""),
        "reasoning_effort": old_group.get("reasoning_effort", ""),
        "web_queries": old_group.get("web_queries", 0),
        "derived": True,
        "lost_members": lost,
    }
    # the sweep's declared picks survive only where their ticker stayed; a
    # departed pick is replaced by the top surviving row of that side, with its
    # own fields standing in for the case — an admitted, marked derivation
    for side in ("long", "short"):
        old_pick = old_group.get(f"best_{side}") or {}
        ticker = (old_pick.get("ticker") or "").upper()
        if ticker and ticker in members:
            out[f"best_{side}"] = {**old_pick}
        else:
            top = next((r for r in ranking if r["side"] == side), None)
            if top is not None:
                out[f"best_{side}"] = _pick_from_row(top, side)
    if lost:
        out["headline"] = (out["headline"] + f" — membership deduplicated since the sweep: "
                           f"{len(lost)} member(s) now rank under their primary industry "
                           f"({', '.join(lost)}).").strip(" -")
    return out


def _fill_gaps(groups: list[dict], ref: date, quant_by_ticker: dict) -> int:
    """Freshly rank the non-COLD themes the old sweep never judged.

    Dedup changes memberships, and recomputing the radar can push a theme that
    was COLD at sweep time over the line (its uncovered members left, coverage
    and breadth recomputed on the survivors). Derivation cannot invent their
    rankings — there are no rows to reuse — so these get the real thing: the
    sweep's own per-group pass, ~20s of LLM each. Without this, every member
    whose largest theme is one of these sits judged nowhere."""
    from ptm_simple.group_review import _ensure_expectations
    from ptm_simple.radar import _fundamentals, theme_radar
    from ptm_simple.run import load_theme_map
    from ptm_setups.rank import _group_md, rank_group

    theme_map = load_theme_map("wiki")
    have = {g["theme"] for g in groups}
    fund = _fundamentals()
    fill = [theme_radar(e, fund, ref) for e in theme_map["themes"]]
    fill = [r for r in fill if r["theme"] not in have and r["status"] != "COLD"]
    if not fill:
        return 0

    def _needs_date(ticker: str) -> bool:
        from ptm.config import data_dir
        path = data_dir("raw", "expectations", f"{ticker}.json")
        if not path.exists():
            return True
        try:
            return not (json.loads(path.read_text(encoding="utf-8")) or {}).get("earnings_date")
        except Exception:
            return True

    to_fix = sorted({m["ticker"] for r in fill for m in r["members"]
                     if not m.get("covered") or _needs_date(m["ticker"])})
    if to_fix:
        log(f"fill: {len(to_fix)} member(s) missing expectations or a print date — backfilling first")
        _ensure_expectations(to_fix)
        fund = _fundamentals()
        fill = [theme_radar(e, fund, ref) for e in theme_map["themes"]]
        fill = [r for r in fill if r["theme"] not in have and r["status"] != "COLD"]
    for row in fill:
        group = rank_group(row, quant_by_ticker, ref)
        groups.append(group)
        if group.get("members_ranked"):
            _group_md(group, ref)
    log(f"fill: {len(fill)} theme(s) the sweep had COLD now ranked fresh")
    return len(fill)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", help="the sweep's setups JSON to derive from")
    ap.add_argument("--fill-gaps", action="store_true",
                    help="freshly rank non-COLD themes the old sweep never judged "
                    "(dedup can push a theme over the line with no rows to derive)")
    args = ap.parse_args()

    from ptm_setups import setups_dir
    from ptm_setups.rank import _final_candidates, _final_round, _group_md, _leaderboard_md

    old_path = Path(args.old) if args.old else max(
        setups_dir().glob("setups_*.json"), key=lambda p: p.stat().st_mtime)
    old = json.loads(old_path.read_text(encoding="utf-8"))
    ref = date.fromisoformat(old["as_of"])
    log(f"dedupe: deriving from {old_path.name} (as_of {ref.isoformat()}, "
        f"{len(old.get('groups') or [])} group(s))")

    _dedupe_map()
    non_cold, _members = _radar_and_quant(ref)

    old_by_theme = {g["theme"]: g for g in old.get("groups") or []}
    quant_by_ticker = _quant_by_ticker(ref)
    groups, paths = [], []
    for theme, row in non_cold.items():
        old_group = old_by_theme.get(theme)
        if not old_group:
            continue
        g = _derive_group(row, old_group, quant_by_ticker, ref)
        if g is None:
            continue
        groups.append(g)
        if g.get("members_ranked"):
            paths.append(_group_md(g, ref))
    ranked = sum(len(g.get("ranking") or []) for g in groups)
    slots = len({r["ticker"] for g in groups for r in g.get("ranking") or []})
    log(f"derived: {len(groups)} group(s), {ranked} row(s) for {slots} distinct tickers")
    if ranked != slots:
        raise SystemExit("dedupe produced duplicate memberships — refusing to write")

    if args.fill_gaps:
        _fill_gaps(groups, ref, quant_by_ticker)
    derived_note = " DERIVED after one-membership dedup: each ticker ranks only " \
        "under its largest theme; group judgements are the sweep's own (factual cells re-rendered " \
        "from the deduped quant table) and the cross-industry final was re-run."
    note = old.get("note", "") + ("" if "DERIVED after" in old.get("note", "") else derived_note)
    if args.fill_gaps and any(not g.get("derived") for g in groups):
        note += " Themes the sweep had marked COLD but that read non-COLD under the " \
            "deduped map were ranked fresh in this pass."
    payload = {
        "as_of": ref.isoformat(),
        "map_source": "wikipedia-industry",
        "note": note,
        "groups": groups,
        "leaderboard": _final_round(_final_candidates(groups), ref),
    }
    out = setups_dir(f"setups_{ref.isoformat()}.json")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for g in groups:
        if g.get("members_ranked"):
            _group_md(g, ref)
    _leaderboard_md(payload, ref)
    lb = payload["leaderboard"]
    ranked = sum(len(g.get("ranking") or []) for g in payload["groups"])
    log(f"dedupe done: {len(payload['groups'])} group(s), {ranked} row(s), leaderboard "
        f"{len(lb.get('longs') or [])} long / {len(lb.get('shorts') or [])} short -> {out.name}")


def _quant_by_ticker(ref: date) -> dict:
    from ptm_simple.quant import load_quant

    doc = load_quant(ref)
    return {row["ticker"]: row for row in (doc or {}).get("rows") or []}


if __name__ == "__main__":
    main()