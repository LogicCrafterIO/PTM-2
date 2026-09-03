"""Coverage reports and the analyze-all sweep for the simple process.

Every covered member of every non-COLD theme takes the side its own 90d
estimate direction implies and gets a deep dive (cache-first), a forward
brief and a coverage report carrying the theme-relative valuation flag.
No selection, no gates, no book — portfolio construction is out of scope
for this process; trade candidates come from the group review instead.
Everything writes under data/simple/ and ideas/simple/ — the main pipeline
never reads them.
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

    from ptm.config import data_dir

    path = data_dir("curated", "yahoo_fundamentals.csv")
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


def _theme_ctx_md(group: dict, idea: dict) -> str:
    """The Theme context block, shared by every coverage report."""
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
    flag) as the print-focused qual — this is the layer the flag is judged
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
                f"gate-processed. Side follows the name's own 90d estimate direction.*\n\n"
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
    a coverage report carrying the theme-relative valuation flag.

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