"""Dive hook, book assembly and idea reports for the simple process.

The dive is PTM's engine run as-is on the shortlist; the adapter verdict
(qual_from_deepdive) supplies the quantified evidence the getting-paid gate
consumes. Idea reports and the book write under data/simple/ and
ideas/simple/ — the main pipeline never reads them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ptm.log import log
from ptm_simple import simple_dir, simple_ideas_dir


def run_shortlist_dives(picks: list[dict], force: bool = False) -> dict[str, dict | None]:
    """Run the standard deep dive + adapter verdict for each shortlisted member.

    Returns {ticker: qual_dict_or_None}. A failed dive returns None and the
    gate fails closed (dive pending) — never silently passes.
    """
    from ptm.deepsearch.pipeline import run_deep_dive
    from ptm.deepsearch.render import render_markdown
    from ptm.deepsearch.verdict import qual_from_deepdive
    from ptm.models import Candidate, Side

    fund = _fundamentals()
    quals: dict[str, dict | None] = {}
    for pick in picks:
        ticker = pick["ticker"]
        row = fund.get(ticker) or {}
        name, sector, industry = str(row.get("name", "") or ""), str(row.get("sector", "") or ""), str(row.get("industry", "") or "")
        side = Side.SHORT if pick.get("side") == "short" else Side.LONG
        log(f"dive {ticker} ({sector}) for the simple process")
        try:
            result = run_deep_dive(ticker, name=name, sector=sector, industry=industry, force=force)
            if result.error:
                log(f"dive {ticker}: {result.error[:100]}")
                quals[ticker] = None
                continue
            cand = Candidate(
                ticker=ticker, name=name, sector=sector, industry=industry, side=side,
                market_cap=row.get("market_cap"), price=row.get("price"),
            )
            qual = qual_from_deepdive(result, cand, render_markdown(result))
            quals[ticker] = qual.model_dump() if hasattr(qual, "model_dump") else dict(qual)
        except Exception as exc:
            log(f"dive {ticker} failed: {exc}")
            quals[ticker] = None
    return quals


def _fundamentals() -> dict[str, dict]:
    import pandas as pd

    path = Path("data/curated/yahoo_fundamentals.csv")
    if not path.exists():
        return {}
    df = pd.read_csv(path).set_index("ticker")
    return {t: row for t, row in df.to_dict(orient="index").items()}


def load_theme_map(source: str = "manual") -> dict:
    """The theme map for a source: 'manual' (the xlsx clusters) or 'wiki'
    (deterministic Wikipedia-industry clusters)."""
    from ptm.io import read_json

    name = "theme_map_wiki.json" if source == "wiki" else "theme_map.json"
    path = simple_dir(name)
    if not path.exists():
        raise SystemExit(f"no theme map for source '{source}': run build-themes first")
    return read_json(path)


def theme_entry(theme_map: dict, theme: str) -> dict | None:
    return next((e for e in theme_map["themes"] if e["theme"] == theme), None)


def select_theme(theme_map: dict, theme: str, ref: date) -> dict:
    """Radar row + deterministic long/short shortlist for one theme."""
    from ptm_simple.radar import theme_radar
    from ptm_simple.select import select_members

    entry = theme_entry(theme_map, theme)
    if entry is None:
        raise SystemExit(f"theme '{theme}' is not in this map")
    row = theme_radar(entry, _fundamentals(), ref)
    return select_members(row)


def run_theme_pass(theme_map: dict, theme: str, ref: date, force: bool = False) -> dict:
    """One full pass for a theme: dive shortlist -> gate -> book -> reports.

    Gate-failed members park on the theme watchlist (the starter pack's
    "nothing dies" rule), alongside any ideas capped out of the book.
    """
    from ptm_simple.gate import gate_theme
    from ptm_simple.radar import theme_radar
    from ptm_simple.select import select_members

    entry = theme_entry(theme_map, theme)
    if entry is None:
        raise SystemExit(f"theme '{theme}' is not in this map")
    row = theme_radar(entry, _fundamentals(), ref)
    if row["status"] == "COLD":
        raise SystemExit(f"{theme} is COLD on {ref} — nothing to run")
    sel = select_members(row)
    picks = [{**e, "side": "long"} for e in sel["long"]] + [{**e, "side": "short"} for e in sel["short"]]
    quals = run_shortlist_dives(picks, force=force)
    gated = gate_theme(sel, row, quals, ref)
    payload = assemble_book([gated], ref)
    # gate-failed members park on the theme watchlist: capped-out book ideas
    # (assemble_book's overflow) are joined by every gated-out name, each with
    # its per-gate results so the watchlist shows why it is waiting
    payload["overflow"] = list(payload["overflow"]) + [p for p in gated.get("parked", []) if p not in payload["overflow"]]
    payload["parked_detail"] = gated.get("parked", [])
    write_book(payload, ref)
    write_idea_reports([gated], ref)
    return payload


def assemble_book(gated: list[dict], ref: date, per_theme: int = 2, max_positions: int = 12) -> dict:
    """Deterministic book: survivors ranked by |breadth| then score, theme-capped."""
    ideas = []
    for g in sorted(gated, key=lambda g: -(g.get("breadth_abs") or 0)):
        for idea in g["ideas"]:
            ideas.append(idea)
    ideas.sort(key=lambda i: (-(i.get("rev90") or 0) if i["side"] == "long" else (i.get("rev90") or 0)))
    counts: dict[str, int] = {}
    book, overflow = [], []
    for idea in ideas:
        key = (idea["theme"], idea["side"])
        if counts.get(key, 0) >= per_theme or len(book) >= max_positions:
            overflow.append(idea)
            continue
        counts[key] = counts.get(key, 0) + 1
        book.append(idea)
    return {"as_of": ref.isoformat(), "book": book, "overflow": overflow}


def write_book(payload: dict, ref: date) -> Path:
    import json

    path = simple_dir(f"simple_book_{ref.isoformat()}.json")
    path.write_text(json.dumps(payload, indent=2, default=str))
    overflow = payload["overflow"]
    watch_path = simple_dir("watchlist.json")
    prev = []
    if watch_path.exists():
        try:
            prev = json.loads(watch_path.read_text()).get("parked", [])
        except Exception:
            prev = []
    seen = {p["ticker"] for p in overflow}
    merged = [p for p in prev if p["ticker"] not in seen] + overflow
    watch_path.write_text(json.dumps({"as_of": ref.isoformat(), "parked": merged}, indent=2, default=str))
    log(f"book: {len(payload['book'])} ideas, {len(overflow)} parked -> {path.name}, watchlist {len(merged)}")
    return path


def write_idea_reports(gated: list[dict], ref: date) -> list[Path]:
    import json

    paths = []
    for group in gated:
        theme_dir = simple_ideas_dir(group["theme"].replace("/", "-").replace(" ", "_"))
        for idea in group["ideas"]:
            path = theme_dir / f"{idea['side']}_{idea['ticker']}_{ref.isoformat()}.md"
            gates_md = "\n".join(
                f"- {'✅' if gate['pass'] else '❌'} **{gate['gate']}** — {gate['detail']}" for gate in idea["gates"]
            )
            path.write_text(
                f"# {idea['side'].upper()} {idea['ticker']} — {group['theme']}\n\n"
                f"*Theme-first simple process · {ref.isoformat()} · deep dive kept, no price targets, no technicals.*\n\n"
                f"## Gatekeeping\n{gates_md}\n\n"
                f"## Theme context\n- Theme lean: {group.get('lean', idea.get('lean', ''))}"
                f" (breadth {group.get('breadth', idea.get('breadth', 0)):+.2f})\n"
                f"- Member 90d estimate change: {idea.get('rev90')}\n"
                f"- Next print: {idea.get('earnings_date', 'unknown')} ({idea.get('days_to_print')}d)\n"
            )
            paths.append(path)
    log(f"idea reports: {len(paths)} written")
    return paths