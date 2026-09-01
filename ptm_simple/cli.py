"""CLI for the simple theme-first process. Nothing here touches ptm/ state.

    .venv/bin/python -m ptm_simple build-themes [--xlsx PATH]
    .venv/bin/python -m ptm_simple radar [--llm] [--theme NAME] [--refresh N]
    .venv/bin/python -m ptm_simple select [--theme NAME]
    .venv/bin/python -m ptm_simple run --theme NAME [--force]   # dive+gate+book
"""

from __future__ import annotations

import argparse
from datetime import date

from ptm.asof import as_of_date
from ptm.log import log


def main() -> None:
    ap = argparse.ArgumentParser(prog="ptm_simple", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build-themes", help="parse the starter pack watchlist into theme_map.json")
    p.add_argument("--xlsx", default="John pre mentoring starterpack.xlsx")

    p = sub.add_parser("radar", help="weekly theme radar (breadth + print calendar)")
    p.add_argument("--theme", help="one theme only")
    p.add_argument("--llm", action="store_true", help="grade WHY-NOW activation per active theme")
    p.add_argument("--refresh", type=int, default=0, help="refresh N member expectation caches per theme")
    p.add_argument("--day", help="override the reference date (YYYY-MM-DD)")

    p = sub.add_parser("select", help="rank members of active themes")
    p.add_argument("--theme", help="one theme only")
    p.add_argument("--day")

    p = sub.add_parser("run", help="full pass for a theme: dive shortlist, gate, book, reports")
    p.add_argument("--theme", required=True)
    p.add_argument("--force", action="store_true", help="redo the dives even when cached")
    p.add_argument("--day")

    args = ap.parse_args()
    ref = as_of_date() if not getattr(args, "day", None) else date.fromisoformat(args.day)

    if args.cmd == "build-themes":
        from ptm_simple.thememap import build_theme_map

        build_theme_map(args.xlsx)
        return

    from ptm.io import read_json
    from ptm_simple import simple_dir

    theme_map = read_json(simple_dir("theme_map.json"))

    if args.cmd == "radar":
        from ptm_simple.radar import run_radar, write_radar
        from ptm_simple.whynow import grade_radar

        rows = run_radar(theme_map, ref, refresh=args.refresh)
        if args.llm:
            grade_radar(rows, only=args.theme)
        rows = [r for r in rows if args.theme is None or r["theme"] == args.theme]
        write_radar(rows, ref)
        for r in rows:
            if r["status"] != "COLD":
                wn = r.get("why_now") or {}
                log(f"  {r['status']:6s} {r['lean']:5s} {r['theme']} breadth {r['breadth']:+.2f} "
                    f"why-now={wn.get('grade', 'n/a')}")
        return

    radar_file = simple_dir(f"radar_{ref.isoformat()}.json")
    if not radar_file.exists():
        raise SystemExit(f"no radar for {ref}: run `ptm_simple radar` first")
    radar_payload = read_json(radar_file)
    member_map = radar_payload.get("members", {})

    if args.cmd == "select":
        from ptm_simple.radar import theme_radar
        from ptm_simple.select import select_members

        fund = _fund()
        for entry in theme_map["themes"]:
            if args.theme and entry["theme"] != args.theme:
                continue
            row = theme_radar(entry, fund, ref)
            if row["status"] == "COLD":
                log(f"  {row['theme']}: COLD — skipping")
                continue
            sel = select_members(row)
            log(f"  {row['status']} {row['theme']}: long {[e['ticker'] for e in sel['long']]}, "
                f"short {[e['ticker'] for e in sel['short']]}")
        return

    if args.cmd == "run":
        from ptm_simple.gate import gate_theme
        from ptm_simple.radar import theme_radar
        from ptm_simple.run import assemble_book, run_shortlist_dives, write_book, write_idea_reports
        from ptm_simple.select import select_members

        entry = next((e for e in theme_map["themes"] if e["theme"] == args.theme), None)
        if entry is None:
            raise SystemExit(f"theme '{args.theme}' not in the map")
        row = theme_radar(entry, _fund(), ref)
        if row["status"] == "COLD":
            raise SystemExit(f"{args.theme} is COLD on {ref} — nothing to run")
        sel = select_members(row)
        picks = [
            {**e, "side": "long"} for e in sel["long"]
        ] + [{**e, "side": "short"} for e in sel["short"]]
        quals = run_shortlist_dives(picks, force=args.force)
        gated = gate_theme(sel, row, quals, ref)
        payload = assemble_book([gated], ref)
        write_book(payload, ref)
        write_idea_reports([gated], ref)
        log(f"run {args.theme} done: {len(payload['book'])} idea(s) in the book")
        return


def _fund() -> dict:
    import pandas as pd
    from pathlib import Path

    path = Path("data/curated/yahoo_fundamentals.csv")
    if not path.exists():
        return {}
    df = pd.read_csv(path).set_index("ticker")
    return {t: row for t, row in df.to_dict(orient="index").items()}


if __name__ == "__main__":
    main()