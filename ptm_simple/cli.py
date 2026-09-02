"""CLI for the simple theme-first process. Nothing here touches ptm/ state.

    .venv/bin/python -m ptm_simple build-themes [--xlsx PATH] [--map manual|wiki]
    .venv/bin/python -m ptm_simple radar [--map manual|wiki] [--llm] [--theme NAME] [--refresh N]
    .venv/bin/python -m ptm_simple refresh-fundamentals [--map manual|wiki] [--all] [--force]
        [--estimates] [--no-prices]  # fresh fundamentals for the quant table
    .venv/bin/python -m ptm_simple analyze-all [--map manual|wiki] [--force]
        # qual coverage for EVERY member of every non-COLD theme (dives cache-first)
    .venv/bin/python -m ptm_simple group-review [--map manual|wiki] [--theme NAME]
        # one pass per non-COLD theme: is each valuation flag justified by the forward case?
"""

from __future__ import annotations

import argparse
from datetime import date

from ptm.asof import as_of_date
from ptm.log import log


def main() -> None:
    ap = argparse.ArgumentParser(prog="ptm_simple", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_map(p: argparse.ArgumentParser) -> None:
        p.add_argument("--map", dest="map", default="manual", choices=("manual", "wiki"),
                       help="theme source: the xlsx clusters or Wikipedia industries")

    p = sub.add_parser("build-themes", help="build a theme map (xlsx clusters or Wikipedia industries)")
    p.add_argument("--xlsx", default="John pre mentoring starterpack.xlsx")
    add_map(p)
    p.add_argument("--refresh", action="store_true", help="wiki: refetch every ticker (ignores cache)")

    p = sub.add_parser("radar", help="weekly theme radar (breadth + print calendar)")
    p.add_argument("--theme", help="one theme only")
    p.add_argument("--llm", action="store_true", help="grade WHY-NOW activation per active theme")
    p.add_argument("--refresh", type=int, default=0, help="refresh N member expectation caches per theme")
    p.add_argument("--day", help="override the reference date (YYYY-MM-DD)")
    add_map(p)

    p = sub.add_parser(
        "refresh-fundamentals",
        help="fetch fresh fundamentals for the simple universe (prices + EDGAR rows at the run date), "
        "then rebuild the quant table and re-render reports",
    )
    p.add_argument("--all", action="store_true", help="whole theme map instead of non-COLD themes only")
    p.add_argument("--force", action="store_true", help="re-pull EDGAR rows even when cached for the run date")
    p.add_argument("--estimates", action="store_true", help="also refresh analyst-consensus caches (forward EPS)")
    p.add_argument("--no-prices", action="store_true", help="skip the yfinance price refresh")
    p.add_argument("--day")
    add_map(p)

    p = sub.add_parser(
        "analyze-all",
        help="qualitative coverage for EVERY covered member of every non-COLD theme: dive (cache-first), "
        "forward brief, coverage report with the theme-relative valuation flag — no selection, no gates",
    )
    p.add_argument("--force", action="store_true", help="re-run dives even when cached")
    p.add_argument(
        "--cached-dives-only", action="store_true",
        help="fast pass: only names whose deep dive is already cached (briefs only, ~1 min per name); "
        "the rest are left for a later full run",
    )
    p.add_argument("--day")
    add_map(p)

    p = sub.add_parser(
        "group-review",
        help="one LLM pass per non-COLD theme: judge whether each member's theme-relative valuation "
        "flag (premium/discount vs the theme median) is justified by forward-looking fundamentals "
        "and catalysts — commentary, not a gate",
    )
    p.add_argument("--theme", help="review a single theme instead of every non-COLD one")
    p.add_argument("--day")
    add_map(p)

    args = ap.parse_args()
    ref = as_of_date() if not getattr(args, "day", None) else date.fromisoformat(args.day)

    if args.cmd == "build-themes":
        if getattr(args, "map", "manual") == "wiki":
            from ptm_simple.wiki_themes import build_theme_map_wiki

            build_theme_map_wiki()
        else:
            from ptm_simple.thememap import build_theme_map

            build_theme_map(args.xlsx)
        return

    from ptm_simple.run import load_theme_map

    theme_map = load_theme_map(args.map)

    if args.cmd == "radar":
        from ptm_simple.radar import run_radar, write_radar
        from ptm_simple.whynow import grade_radar

        rows = run_radar(theme_map, ref, refresh=args.refresh)
        if args.llm:
            grade_radar(rows, only=args.theme)
        rows = [r for r in rows if args.theme is None or r["theme"] == args.theme]
        write_radar(rows, ref, theme_map)
        for r in rows:
            if r["status"] != "COLD":
                wn = r.get("why_now") or {}
                log(f"  {r['status']:6s} {r['lean']:5s} {r['theme']} breadth {r['breadth']:+.2f} "
                    f"why-now={wn.get('grade', 'n/a')}")
        return

    from ptm.io import read_json
    from ptm_simple import simple_dir

    radar_file = simple_dir(f"radar_{ref.isoformat()}.json")
    if not radar_file.exists():
        raise SystemExit(f"no radar for {ref}: run `ptm_simple radar` first")

    if args.cmd == "refresh-fundamentals":
        from ptm_simple.refresh import refresh_fundamentals

        out = refresh_fundamentals(
            source=args.map,
            ref=ref,
            non_cold_only=not args.all,
            force=args.force,
            with_estimates=args.estimates,
            with_prices=not args.no_prices,
        )
        log(f"refresh-fundamentals done: {out['fundamentals_rows']} rows, quant {out['quant_rows']}, "
            f"reports {out['reports']} in {out['elapsed_s']}s")
        return

    if args.cmd == "analyze-all":
        from ptm_simple.run import analyze_all_pass

        out = analyze_all_pass(theme_map, ref, force=args.force, cached_dives_only=args.cached_dives_only)
        log(f"analyze-all done: {out['members']} member(s) in {out['themes']} non-COLD theme(s), "
            f"{out['skipped']} skipped, {out['reports']} coverage reports")
        return

    if args.cmd == "group-review":
        from ptm_simple.group_review import run_group_review

        out = run_group_review(source=args.map, ref=ref, theme=args.theme)
        log(f"group-review done: {out['themes']} theme(s), {out['judged']} member(s) judged, "
            f"{out['markdown']} markdown file(s)")
        return

if __name__ == "__main__":
    main()