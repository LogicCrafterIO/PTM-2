"""CLI for the group-only ranking process. Nothing here touches ptm/ state.

The deterministic front half is SHARED with the simple process — same theme
map, same weekly radar, same quant table, same artifacts under data/simple/ —
so it is still run from there:

    .venv/Scripts/python.exe -m ptm_simple build-themes --map wiki
    .venv/Scripts/python.exe -m ptm_simple radar --map wiki
    .venv/Scripts/python.exe -m ptm_simple refresh-fundamentals --map wiki

Then the qualitative half, which is this module's own and needs no dives:

    .venv/Scripts/python.exe -m ptm_setups rank [--map manual|wiki] [--theme NAME]
        [--no-final] [--day YYYY-MM-DD]

`rank` runs ONE pass per non-COLD industry over all of its members at once,
ordering them as long and short setups into the next print, then one
cross-industry final over the winners. The viewer's Setups tab runs the same
thing, including the shared stages, from the browser.
"""

from __future__ import annotations

import argparse
from datetime import date

from ptm.asof import as_of_date
from ptm.log import log


def main() -> None:
    ap = argparse.ArgumentParser(prog="ptm_setups", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser(
        "rank",
        help="one ranking pass per non-COLD industry over ALL its members (best longs and shorts into "
        "the next print, on fundamentals and valuation — no technicals, no per-name dive), then one "
        "cross-industry final over the winners",
    )
    p.add_argument("--map", dest="map", default="manual", choices=("manual", "wiki"),
                   help="theme source: the xlsx clusters or Wikipedia industries")
    p.add_argument("--theme", help="rank a single industry instead of every non-COLD one")
    p.add_argument("--no-final", action="store_true",
                   help="skip the cross-industry final; per-industry rankings only")
    p.add_argument("--model", help="override the ranking model for this run (default: "
                                   "OLLAMA_SETUPS_MODEL, currently glm-5.3-flash)")
    p.add_argument("--day", help="override the reference date (YYYY-MM-DD)")

    args = ap.parse_args()
    ref = as_of_date() if not getattr(args, "day", None) else date.fromisoformat(args.day)

    if args.cmd == "rank":
        from ptm_setups.rank import run_setups

        out = run_setups(source=args.map, ref=ref, theme=args.theme,
                         with_final=not args.no_final, model=args.model)
        log(f"setups rank done: {out['groups']} group(s), {out['ranked']} member(s) ranked, "
            f"{out['llm_groups']} judged, leaderboard {out['longs']} long / {out['shorts']} short, "
            f"{out['markdown']} markdown file(s)")
        return


if __name__ == "__main__":
    main()
