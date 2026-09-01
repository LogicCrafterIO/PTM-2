"""CLI for the simple theme-first process. Nothing here touches ptm/ state.

    .venv/bin/python -m ptm_simple build-themes [--xlsx PATH] [--map manual|wiki]
    .venv/bin/python -m ptm_simple radar [--map manual|wiki] [--llm] [--theme NAME] [--refresh N]
    .venv/bin/python -m ptm_simple select --theme NAME [--map manual|wiki]
    .venv/bin/python -m ptm_simple run --theme NAME [--map manual|wiki] [--force]
    .venv/bin/python -m ptm_simple run --all [--map manual|wiki] [--force]  # sweep non-COLD themes
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

    p = sub.add_parser("select", help="rank members of active themes")
    p.add_argument("--theme", help="one theme only")
    p.add_argument("--day")
    add_map(p)

    p = sub.add_parser("run", help="full pass for a theme: dive shortlist, gate, book, reports")
    p.add_argument("--theme", help="one theme; omit with --all to sweep every non-COLD theme")
    p.add_argument("--all", action="store_true", help="run every non-COLD theme and assemble one book")
    p.add_argument("--force", action="store_true", help="redo the dives even when cached")
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

    if args.cmd == "select":
        from ptm_simple.run import select_theme, theme_entry

        for entry in theme_map["themes"]:
            if args.theme and entry["theme"] != args.theme:
                continue
            sel = select_theme(theme_map, entry["theme"], ref)
            if sel["status"] == "COLD":
                log(f"  {sel['theme']}: COLD — skipping")
                continue
            log(f"  {sel['status']} {sel['theme']} ({sel['lean']}): "
                f"long {[e['ticker'] for e in sel['long']]}, short {[e['ticker'] for e in sel['short']]}")
        return

    if args.cmd == "run":
        from ptm_simple.run import run_active_pass, run_theme_pass

        if getattr(args, "all", False):
            payload = run_active_pass(theme_map, ref, force=args.force)
            log(f"run-all done: {payload.get('themes_run', 0)} theme(s), "
                f"{len(payload['book'])} idea(s) in the book, {len(payload['overflow'])} parked")
        else:
            if not args.theme:
                raise SystemExit("run needs --theme NAME (or --all for every non-COLD theme)")
            payload = run_theme_pass(theme_map, args.theme, ref, force=args.force)
            log(f"run {args.theme} done: {len(payload['book'])} idea(s) in the book")
        return


if __name__ == "__main__":
    main()