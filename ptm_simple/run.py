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
    payload = assemble_book([gated], ref, source=theme_map.get("source"))
    # gate-failed members park on the theme watchlist: capped-out book ideas
    # (assemble_book's overflow) are joined by every gated-out name, each with
    # its per-gate results so the watchlist shows why it is waiting
    payload["overflow"] = list(payload["overflow"]) + [p for p in gated.get("parked", []) if p not in payload["overflow"]]
    payload["parked_detail"] = gated.get("parked", [])
    payload["themes_run"] = 1
    write_book(payload, ref)
    from ptm_simple.quant import build_quant

    build_quant(ref, [row])
    write_idea_reports([gated], ref)
    return payload


def run_active_pass(theme_map: dict, ref: date, force: bool = False) -> dict:
    """Sweep EVERY non-COLD theme of the map: dive each shortlist, gate, and
    assemble one book across themes. Dives reuse the shared cache, so a
    weekly rerun only pays for names dived for the first time."""
    from ptm_simple.gate import gate_theme
    from ptm_simple.quant import build_quant
    from ptm_simple.radar import theme_radar
    from ptm_simple.select import select_members

    fund = _fundamentals()
    gated_groups: list[dict] = []
    radar_rows: list[dict] = []
    for entry in theme_map["themes"]:
        row = theme_radar(entry, fund, ref)
        if row["status"] == "COLD":
            continue
        radar_rows.append(row)
        log(f"theme {row['theme']}: {row['status']} ({row['lean']}, breadth {row['breadth']:+.2f})")
        sel = select_members(row)
        picks = [{**e, "side": "long"} for e in sel["long"]] + [{**e, "side": "short"} for e in sel["short"]]
        if not picks:
            log(f"  {row['theme']}: no eligible members — nothing to dive")
            continue
        quals = run_shortlist_dives(picks, force=force)
        gated_groups.append(gate_theme(sel, row, quals, ref))
    payload = assemble_book(gated_groups, ref, source=theme_map.get("source"))
    parked: list[dict] = []
    for g in gated_groups:
        parked.extend(g.get("parked", []))
    payload["overflow"] = list(payload["overflow"]) + [p for p in parked if p not in payload["overflow"]]
    payload["parked_detail"] = parked
    payload["themes_run"] = len(gated_groups)
    write_book(payload, ref)
    build_quant(ref, radar_rows)
    write_idea_reports(gated_groups, ref)
    return payload


def assemble_book(gated: list[dict], ref: date, per_theme: int = 2, max_positions: int = 12, source: str | None = None) -> dict:
    """Deterministic book with SIDE PARITY: half the slots are reserved for
    shorts; when gate-passed shorts are fewer than half they all get in and
    longs fill the rest (and when one side runs out entirely the other
    backfills the remainder). The theme cap (per_theme per theme+side) still
    applies.

    Within each side the strongest 90d revision first, saturated at ±5% — the
    same materiality selection uses, so one data-glitch revision (a +1369%
    base effect in the expectations cache) cannot outrank every real signal.
    Both sides rank strongest-first: the old mixed sort ranked shorts
    weakest-first, which the parity rule would have promoted into the book.
    """

    def _sort_key(idea: dict) -> tuple[float, float]:
        # (saturated magnitude, raw |rev90|): the saturation keeps a data-glitch
        # revision (+1369% base effect) from outranking real signals; the raw
        # magnitude only breaks ties AMONG saturated ideas.
        rev = idea.get("rev90")
        if rev is None:
            return (0.0, 0.0)
        magnitude = min(abs(rev) / 5.0, 1.0)
        signed = magnitude if (idea["side"] == "long") == (rev > 0) else -magnitude
        return (signed, abs(rev))

    def _take(pool: list[dict], budget: int, counts: dict[str, int]) -> tuple[list[dict], list[dict]]:
        picked, rest = [], []
        for idea in pool:
            key = (idea["theme"], idea["side"])
            if len(picked) < budget and counts.get(key, 0) < per_theme:
                counts[key] = counts.get(key, 0) + 1
                picked.append(idea)
            else:
                rest.append(idea)
        return picked, rest

    survivors = [idea for g in gated for idea in g["ideas"]]
    longs = sorted((i for i in survivors if i["side"] == "long"), key=_sort_key, reverse=True)
    shorts = sorted((i for i in survivors if i["side"] == "short"), key=_sort_key, reverse=True)

    counts: dict[str, int] = {}
    half = max_positions // 2
    short_budget = min(len(shorts), half)
    book_l, rest_l = _take(longs, max_positions - short_budget, counts)
    book_s, rest_s = _take(shorts, short_budget, counts)
    # one side fell short of its half: the other backfills the remainder
    spare = max_positions - len(book_l) - len(book_s)
    if spare > 0 and rest_s:
        more, rest_s = _take(rest_s, spare, counts)
        book_s.extend(more)
    elif spare > 0 and rest_l:
        more, rest_l = _take(rest_l, spare, counts)
        book_l.extend(more)
    return {
        "as_of": ref.isoformat(),
        "source": source,
        "book": book_l + book_s,
        "overflow": rest_l + rest_s,
    }


def write_book(payload: dict, ref: date) -> Path:
    import json

    source = payload.get("source") or "manual"
    stem = "wiki" if "wiki" in str(source) else "manual"
    path = simple_dir(f"simple_book_{stem}_{ref.isoformat()}.json")
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    overflow = payload["overflow"]
    watch_path = simple_dir("watchlist.json")
    prev = []
    if watch_path.exists():
        try:
            prev = json.loads(watch_path.read_text(encoding="utf-8")).get("parked", [])
        except Exception:
            prev = []
    seen = {p["ticker"] for p in overflow} | {i["ticker"] for i in payload["book"]}
    merged = [p for p in prev if p["ticker"] not in seen] + overflow
    watch_path.write_text(json.dumps({"as_of": ref.isoformat(), "parked": merged}, indent=2, default=str), encoding="utf-8")
    log(f"book: {len(payload['book'])} ideas, {len(overflow)} parked -> {path.name}, watchlist {len(merged)}")
    return path


_GATES_HELP = {
    "why_now": (
        "the theme is activating (WARM/ACTIVE revision breadth) AND the name's own 90d estimate "
        "direction agrees with the side — longs need rising estimates, shorts falling ones. The process "
        "never shorts a name whose estimates are rising, nor longs one whose estimates are falling, "
        "whatever the theme is doing (a name going against its theme is a diverger, traded on its own direction)."
    ),
    "early_or_late": (
        "a dated earnings print sits within the 2-4 month trade horizon (1-120 days out). The print itself "
        "may be the catalyst; a print that has just passed parks the idea."
    ),
    "getting_paid": (
        "the deep dive must surface at least one QUANTIFIED evidence item whose measured magnitude is "
        ">= 3% against a core fundamental (revenue, margin, backlog, ...). Quantified means the percentage "
        "appears verbatim in the dive's sourced findings — the gate can never be fed an invented number, "
        "and it is an estimate-impact test, not a price target."
    ),
    "listening": (
        "the theme is not COLD. If the theme goes cold on a later weekly pass, the idea is dropped and "
        "parked on the watchlist — nothing dies, it waits."
    ),
}


def _prune_old_reports(root: Path, ref: date) -> int:
    """Remove idea reports stamped older than this run — the Simple tab shows
    the current book, not a growing archive. Guard: when the run is backdated
    (ref older than the newest report already in the tree) nothing is pruned,
    so a `--day 2026-08-20` pass cannot delete the current book's reports."""
    import re as _re

    stamped = []
    for p in root.rglob("*.md"):
        m = _re.search(r"_(\d{4}-\d{2}-\d{2})\.md$", p.name)
        if m:
            stamped.append((date.fromisoformat(m.group(1)), p))
    if not stamped:
        return 0
    newest = max(d for d, _ in stamped)
    if ref < newest:
        return 0
    removed = 0
    for d, p in stamped:
        if d < ref:
            p.unlink()
            removed += 1
    # drop theme dirs left empty by the prune
    for d in root.rglob("*"):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
    if removed:
        log(f"pruned {removed} report(s) older than {ref.isoformat()}")
    return removed


def _quant_section_md(ticker: str, ref: date) -> str:
    """Deterministic quant snapshot for the report — reference numbers only,
    never a ranking. Rendered from data/simple/quant_<ref>.json when present."""
    from ptm_simple.quant import load_quant

    quant = load_quant(ref)
    if not quant:
        return ""
    row = next((r for r in quant["rows"] if r["ticker"] == ticker), None)
    if not row or row.get("note"):
        return ""
    def _fmt(v, suffix: str = "", pct: bool = False) -> str:
        if v is None:
            return "—"
        if pct:
            return f"{v * 100:+.1f}%{suffix}" if suffix else f"{v * 100:+.1f}%"
        return f"{v:,.2f}{suffix}"

    def _mcap(v) -> str:
        if v is None:
            return "—"
        return f"${v / 1e9:.1f}B" if abs(v) >= 1e9 else f"${v / 1e6:.0f}M"

    rev90 = row.get("rev90")
    rev90_md = "—" if rev90 is None else f"{rev90:+.1f}%"  # rev90 arrives as a percentage
    flag = row.get("flag") or "n/a"
    flag_detail = row.get("flag_detail") or ""
    lines = [
        f"| Price | {_fmt(row.get('price'))} |",
        f"| Market cap | {_mcap(row.get('market_cap'))} |",
        f"| Revenue (latest filing) | {_mcap(row.get('revenue'))} |",
        f"| **Price / Sales** | **{_fmt(row.get('ps'))}x** |",
        f"| FY1 EPS (consensus) | {_fmt(row.get('eps1'))} |",
        f"| FY2 EPS (consensus) | {_fmt(row.get('eps2'))} |",
        f"| EG1 → EG2 | {_fmt(row.get('eg1'), pct=True)} → {_fmt(row.get('eg2'), pct=True)} |",
        f"| PE1 | {_fmt(row.get('pe1'))}x |",
        f"| PE2 | {_fmt(row.get('pe2'))}x |",
        f"| PEG1 | {_fmt(row.get('peg1'))} |",
        f"| PEG2 | {_fmt(row.get('peg2'))} |",
        f"| **Valuation flag (vs theme)** | **{flag}** — {flag_detail} |",
        f"| rev90 (own estimates) | {rev90_md} |",
    ]
    as_of = row.get("fundamentals_as_of", "")
    as_of_note = f" Fundamentals as of {as_of}." if as_of else ""
    return (
        "## Quant snapshot (deterministic)\n\n"
        "| metric | value |\n|---|---|\n" + "\n".join(lines) + "\n\n"
        f"*Reference numbers from the cached fundamentals table (EDGAR XBRL + analyst consensus, "
        f"basis: {row.get('forward_source') or 'n/a'}).{as_of_note} Not a ranking, not a gate — read the qual brief against these.*"
    )


def write_idea_reports(gated: list[dict], ref: date) -> list[Path]:
    _prune_old_reports(simple_ideas_dir(), ref)
    paths = []
    for group in gated:
        theme_dir = simple_ideas_dir(group["theme"].replace("/", "-").replace(" ", "_"))
        for idea in group["ideas"]:
            path = theme_dir / f"{idea['side']}_{idea['ticker']}_{ref.isoformat()}.md"
            gates_md = "\n".join(
                f"- {'✅' if gate['pass'] else '❌'} **{gate['gate']}** — {gate['detail']}" for gate in idea["gates"]
            )
            theme_ctx = _theme_ctx_md(group, idea)
            brief_md = _brief_and_catalysts_md(group, idea, ref)
            quant_md = _quant_section_md(idea["ticker"], ref)
            path.write_text(
                f"# {idea['side'].upper()} {idea['ticker']} — {group['theme']}\n\n"
                f"*Theme-first simple process · {ref.isoformat()} · deep dive kept, no price targets, no technicals.*\n\n"
                f"## Gatekeeping\n{gates_md}\n\n"
                f"**What each gate checks**\n" + "\n".join(
                    f"- **{gate['gate']}** — {_GATES_HELP[gate['gate']]}" for gate in idea["gates"] if gate["gate"] in _GATES_HELP
                ) + "\n\n"
                f"## Theme context\n{theme_ctx}\n\n"
                + brief_md + "\n\n"
                + quant_md + "\n\n"
                f"## Underlying research\n"
                f"- Deep dive: `data/raw/deepsearch/runs/{idea['ticker']}.json` — rendered in the "
                f"viewer's Deep dives tab (stance, bull/bear debate, sourced findings, falsifiers).",
                encoding="utf-8",
            )
            paths.append(path)
    log(f"idea reports: {len(paths)} written")
    return paths


def _theme_ctx_md(group: dict, idea: dict) -> str:
    """The Theme context block, shared by gated and coverage reports."""
    breadth = group.get("breadth", idea.get("breadth", 0.0))
    lean = group.get("lean", idea.get("lean", ""))
    rev90 = idea.get("rev90")
    with_theme = "with the theme" if (rev90 or 0) * breadth >= 0 else "AGAINST the theme (diverger)"
    coverage = (
        f"{group.get('members_covered', '?')} of {group.get('members_total', '?')} members have fresh estimate caches"
        if group.get("members_total") else None
    )
    thesis = str(group.get("thesis") or "").strip() or "(none written for this theme)"
    bellwether = group.get("bellwether")
    lines = [
        f"- Theme status: {group.get('status', 'n/a')}, lean {lean} (breadth {breadth:+.2f}) — share of covered "
        f"members revising up minus share revising down over 90d (each move > ±0.5%)",
        f"- Thesis: {thesis}",
    ]
    if coverage:
        lines.append(f"- Coverage: {coverage}")
    if bellwether:
        lines.append(f"- Bellwether (largest member printing within 14 days): {bellwether}")
    lines.extend(
        [
            f"- This name vs its theme: {with_theme}",
            f"- Member 90d estimate change (rev90): {rev90:+.2f}% — the name's own FY1 EPS estimate "
            f"{'rise' if (rev90 or 0) > 0 else 'fall'} over the last 90 days",
            f"- Next print: {idea.get('earnings_date', 'unknown')} ({idea.get('days_to_print')}d) — the "
            f"catalyst the 2-4 month horizon is built around",
        ]
    )
    return "\n".join(lines)


def _brief_and_catalysts_md(group: dict, idea: dict, ref: date) -> str:
    """The forward brief + catalysts block, shared by both report kinds."""
    from ptm_simple.brief import forward_brief

    brief = forward_brief(idea["ticker"], idea["side"], group, ref)
    if not brief:
        return "\n## Why & why now (forward-looking)\n- (brief unavailable — cached dive only)"
    pts_md = "\n".join(f"{i}. {p}" for i, p in enumerate(brief["points"], 1))
    cat_lines = []
    if idea.get("earnings_date"):
        cat_lines.append(
            f"- **{idea['ticker']} print** — {idea['earnings_date']} ({idea.get('days_to_print')}d) — "
            f"the dated catalyst this idea is built around"
        )
    for pp in (group.get("peer_prints") or [])[:6]:
        if pp.get("ticker") != idea["ticker"] and pp.get("earnings_date"):
            cat_lines.append(
                f"- Peer print: **{pp['ticker']}** — {pp['earnings_date']} ({pp.get('days_to_print')}d) — "
                f"same-theme read-through"
            )
    for c in brief["catalysts"][:4]:
        line = f"- {c['event']}"
        if c["window"]:
            line += f" — {c['window']}"
        if c["expected"]:
            line += f" — if it lands: {c['expected']}"
        cat_lines.append(line)
    return (
        f"\n## Why & why now (forward-looking)\n{pts_md}\n\n"
        f"## Catalysts\n"
        + ("\n".join(cat_lines) if cat_lines else "- (none dated)")
    )


def write_coverage_reports(groups: list[dict], ref: date) -> list[Path]:
    """Per-member research reports for analyze-all: NO selection, NO gates.

    Same theme context / forward brief / quant snapshot (with the valuation
    flag) as the gated reports — this is the qual layer the flag is judged
    against. The coverage_ prefix keeps the two report families apart."""
    paths = []
    for group in groups:
        theme_dir = simple_ideas_dir(group["theme"].replace("/", "-").replace(" ", "_"))
        for idea in group["ideas"]:
            path = theme_dir / f"coverage_{idea['side']}_{idea['ticker']}_{ref.isoformat()}.md"
            theme_ctx = _theme_ctx_md(group, idea)
            brief_md = _brief_and_catalysts_md(group, idea, ref)
            quant_md = _quant_section_md(idea["ticker"], ref)
            path.write_text(
                f"# COVERAGE {idea['side'].upper()} {idea['ticker']} — {group['theme']}\n\n"
                f"*Theme-first simple process · {ref.isoformat()} · full-membership research coverage — not "
                f"gate-processed, not in the book. Side follows the name's own 90d estimate direction.*\n\n"
                f"## Theme context\n{theme_ctx}\n\n"
                + brief_md + "\n\n"
                + quant_md + "\n\n"
                f"## Underlying research\n"
                f"- Deep dive: `data/raw/deepsearch/runs/{idea['ticker']}.json` — rendered in the "
                f"viewer's Deep dives tab (stance, bull/bear debate, sourced findings, falsifiers).",
                encoding="utf-8",
            )
            paths.append(path)
    log(f"coverage reports: {len(paths)} written")
    return paths


def analyze_all_pass(theme_map: dict, ref: date, force: bool = False, cached_dives_only: bool = False) -> dict:
    """Qualitative coverage for EVERY covered member of every non-COLD theme.

    No selection, no gates: each member takes the side its own 90d estimate
    direction implies (long rising, short falling; flat or uncached members are
    skipped — they have no directional story), then a deep dive (cached dives
    are free; a first-time dive costs minutes of LLM each), a forward brief and
    a coverage report carrying the theme-relative valuation flag. The gated
    book above this layer is untouched.

    cached_dives_only restricts coverage to names whose dive is already cached —
    the fast pass (briefs only, ~1 min per name); the rest wait for a full run."""
    from ptm_simple.quant import build_quant
    from ptm_simple.radar import theme_radar

    fund = _fundamentals()
    groups: list[dict] = []
    non_cold_rows: list[dict] = []
    skipped = 0
    no_dive = 0
    for entry in theme_map["themes"]:
        row = theme_radar(entry, fund, ref)
        if row["status"] == "COLD":
            continue
        non_cold_rows.append(row)
        ideas = []
        for m in row["members"]:
            rev = m.get("rev90")
            side = "long" if (rev or 0) > 0.5 else "short" if (rev or 0) < -0.5 else None
            if not m.get("covered") or side is None:
                skipped += 1
                continue
            if cached_dives_only and not _has_dive(m["ticker"]):
                no_dive += 1
                continue
            ideas.append({
                "ticker": m["ticker"], "side": side, "rev90": rev,
                "earnings_date": m.get("earnings_date"), "days_to_print": m.get("days_to_print"),
                "_member": m,
            })
        if not ideas:
            continue
        groups.append({
            "theme": row["theme"], "ideas": ideas, "status": row["status"],
            "lean": row["lean"], "breadth": row["breadth"], "thesis": row.get("thesis", ""),
            "bellwether": row.get("bellwether"),
            "members_covered": row.get("members_covered"), "members_total": row.get("members_total"),
            "peer_prints": [
                {"ticker": m["ticker"], "earnings_date": m.get("earnings_date"), "days_to_print": m.get("days_to_print")}
                for m in row["members"]
                if m.get("days_to_print") is not None and 0 <= m["days_to_print"] <= 120
            ],
        })
    total = sum(len(g["ideas"]) for g in groups)
    log(f"analyze-all: {total} member(s) across {len(groups)} non-COLD theme(s), {skipped} skipped "
        f"(flat or uncached estimates)"
        + (f", {no_dive} without a cached dive (cached-dives-only)" if cached_dives_only else "")
        + " — dives run only where the cache misses")
    # the quant table needs no dives, so the valuation flags are ready before
    # the first one runs; each theme then dives -> briefs -> reports in turn, so
    # coverage appears theme by theme instead of only at the very end
    build_quant(ref, non_cold_rows)
    reports = 0
    for group in groups:
        if not group["ideas"]:
            continue
        theme_picks = [{**i.pop("_member"), "side": i["side"]} for i in group["ideas"]]
        run_shortlist_dives(theme_picks, force=force)
        reports += len(write_coverage_reports([group], ref))
    return {"themes": len(groups), "members": total, "skipped": skipped, "reports": reports}


def _has_dive(ticker: str) -> bool:
    """True when a cached deep dive exists for the ticker (same path the brief reads)."""
    from ptm.config import data_dir

    return (data_dir("raw", "deepsearch", "runs", f"{ticker}.json")).exists()