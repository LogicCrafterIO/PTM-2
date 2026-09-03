"""Backfill the forward-looking why-not-COLD judgement into an existing artifact.

The group ranking pass now returns `why_not_cold` ({direction, reason}) — the
qualitative reason an industry is not COLD, stated as upside or downside and
argued from what happens NEXT (order flow into the coming prints, survey and
backlog direction, the trajectory guidance and revisions imply), never a
restatement of the 90-day revision table. Groups ranked before that field
existed get it here without re-running their rankings: each group's rows, best
picks and prose stand untouched, and one short LLM call per group reads the
group's own ranking plus fresh search snippets and the ISM demand snapshot and
writes only this field. Groups that already carry it are skipped, so reruns are
cheap and nothing is overwritten twice.

    python scripts/cold_reasons.py                 # newest setups JSON
    python scripts/cold_reasons.py --from data/setups/setups_2026-09-02.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ptm.log import log


def _user_message(group: dict, macro: str, searches: list[dict], ref) -> str:
    theme = group.get("theme") or ""
    lines = [
        f"Today: {ref.isoformat()}",
        f"Industry group: {theme} — radar status {group.get('status')}, lean {group.get('lean')} "
        f"(breadth {group.get('breadth', 0):+.2f})",
    ]
    if macro:
        lines.append(macro)
    lines.append(
        "This group's ranking, already on file — the reason must be consistent with it, and must say "
        "so where the forward evidence is not:"
    )
    for r in group.get("ranking") or []:
        lines.append(f"  {r['rank']}. {r['ticker']} — {r['side']}, {r.get('conviction') or '?'}"
                     + (f", ranked on: {r['ranked_on']}" if r.get("ranked_on") else ""))
    for side in ("long", "short"):
        pick = group.get(f"best_{side}") or {}
        if pick.get("ticker"):
            thesis = str(pick.get("thesis") or "")[:200]
            lines.append(f"  best_{side}: {pick.get('ticker')} — {thesis}")
    if searches:
        lines.append(
            "Web-search snippets for this industry (developments since the filings; recency "
            "UNVERIFIED — leads, not dated facts):"
        )
        for s in searches:
            lines.append(f"- {s['title']}: {s['snippet']}" if s.get("title") else f"- {s['snippet']}")
    else:
        lines.append("No web snippets available — argue from the ISM demand data and the ranking above only.")
    lines.append(
        "Return JSON keys: direction (exactly one of: upside, downside — which side the "
        "forward-looking reason favours) and reason (one or two sentences, at most 460 characters). "
        "The reason must be FORWARD-LOOKING: what happens NEXT from here — the order flow and demand "
        "the next prints will report, the trajectory guidance and revisions imply, what surveys and "
        "backlogs point to. It is NOT a restatement of the 90-day revision data listed above, and it "
        "is not valuation language."
    )
    return "\n".join(lines)


_COLD_SYSTEM = (
    "You are the same long/short industry ranking pass that produced a group's setups, asked now for "
    "ONE field only: why the industry is not COLD. The radar flags a group COLD when its members' "
    "90-day estimate revisions are flat or absent — a group that is not COLD has a measurable "
    "revision lean, and your job is to say, qualitatively and FORWARD-LOOKINGLY, why that lean is "
    "tradeable: whether it is to the UPSIDE or the DOWNSIDE and why — what happens next from here "
    "(order flow and demand the coming prints will report, the trajectory guidance and revisions "
    "imply, what surveys, backlogs and the searched developments point to). Be specific to this "
    "industry; do not hedge into both-sides-ism; when the forward evidence argues against the "
    "revision breadth, say so plainly in the reason and let direction say which side that favours."
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="source", help="the setups JSON to backfill (default: the newest)")
    args = ap.parse_args()

    from ptm_setups import setups_dir
    from ptm_setups.rank import _group_md, _macro_demand_line, _why_not_cold
    from ptm_setups.search import group_snippets
    from ptm_simple.run import load_theme_map
    from ptm.llm import chat_json, llm_available, setups_model

    path = Path(args.source) if args.source else max(
        setups_dir().glob("setups_*.json"), key=lambda p: p.stat().st_mtime)
    doc = json.loads(path.read_text(encoding="utf-8"))
    ref = date.fromisoformat(doc["as_of"])

    theme_map = load_theme_map("wiki")
    rows_by_theme = {t["theme"]: t for t in theme_map.get("themes") or []}
    macro = _macro_demand_line()
    # the map's members are ticker strings; the search query wants {ticker, name}
    # dicts, and the quant table written by the front half carries the names
    from ptm_simple import simple_dir

    quant_path = simple_dir(f"quant_{ref.isoformat()}.json")
    names = {r["ticker"]: r for r in json.loads(quant_path.read_text(encoding="utf-8")).get("rows") or []} \
        if quant_path.exists() else {}

    if not llm_available():
        raise SystemExit("no LLM key — cannot backfill the why-not-COLD field")
    model = setups_model()
    filled, failed = 0, 0
    groups = doc.get("groups") or []
    for g in groups:
        if (g.get("why_not_cold") or {}).get("reason"):
            continue
        if not (g.get("llm_used") and g.get("ranking")):
            continue
        theme = g.get("theme") or ""
        members = [{"ticker": t, "name": (names.get(t) or {}).get("name") or ""}
                   for t in rows_by_theme.get(theme, {}).get("members") or []]
        web = group_snippets(theme, members, ref)
        searches = (web or {}).get("searches") or []
        try:
            payload = chat_json(_COLD_SYSTEM, _user_message(g, macro, searches, ref),
                                model=model, max_tokens=1200, reasoning_effort="low", timeout=180)
        except Exception as exc:
            log(f"cold-reason {theme}: FAIL {str(exc)[:120]}")
            failed += 1
            continue
        # the mini-pass returns {direction, reason} at the top level; the
        # validator reads the group-pass shape (payload.why_not_cold), so wrap
        field = _why_not_cold({"why_not_cold": payload})
        if not field:
            log(f"cold-reason {theme}: unusable answer — skipped: "
                f"{json.dumps(payload)[:160]}")
            failed += 1
            continue
        g["why_not_cold"] = field
        filled += 1
        log(f"cold-reason {theme}: {field['direction']} — {field['reason'][:80]}...")
    if not filled:
        log(f"cold-reason: nothing filled ({len(groups)} group(s) seen, {failed} failure(s))")
        return
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    for g in groups:
        if (g.get("why_not_cold") or {}).get("reason"):
            _group_md(g, ref)
    log(f"cold-reason done: {filled} group(s) filled, {failed} failure(s) -> {path.name}")


if __name__ == "__main__":
    main()