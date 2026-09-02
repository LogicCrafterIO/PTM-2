"""The optional LLM stage: grade WHY-NOW activation for a theme.

One small call per theme, run only when requested (--llm). The model receives
the theme's members, its measured breadth and print calendar, and grades the
activation GREAT / GOOD / NONE with up to three reasons. Its knowledge is
context, not evidence — every quantified claim it makes is a hypothesis the
deep dive must verify, so the output is advisory text on the radar row and
never gates anything by itself.
"""

from __future__ import annotations

import json

from ptm.log import log

_SYSTEM = (
    "You are the WHY-NOW reviewer of a theme-first idea process. You are given a theme, its member "
    "tickers, measured estimate-revision breadth, and upcoming earnings dates. Grade whether the theme "
    "has an activation worth acting on NOW: GREAT (a company-specific event activating members, or a "
    "genuine macro/policy event hitting the cluster), GOOD (a strong sector-specific catalyst), or NONE "
    "(only vague narratives or price moves). Answer ONLY with JSON: "
    '{"grade": "GREAT|GOOD|NONE", "events": ["<event 1>", "<event 2>"], "note": "<one sentence>"} '
    "with at most three events. Do not invent specific numbers or dates you are not given."
)


def grade_theme_activation(row: dict) -> dict | None:
    """Attach {grade, events, note} to a radar row, or None without an LLM."""
    from ptm.llm import chat_json, llm_available

    if not llm_available():
        return None
    members = [m["ticker"] for m in row["members"][:12]]
    prints = [f"{p['ticker']} in {p['days_to_print']}d" for p in row["prints_14d"]]
    prompt = (
        f"Theme: {row['theme']}\n"
        f"Thesis: {row.get('thesis') or '(none written)'}\n"
        f"Members: {', '.join(members)}\n"
        f"Measured 90d estimate-revision breadth: {row['breadth']:+.2f} "
        f"({row['members_covered']}/{row['members_total']} members covered)\n"
        f"Upcoming prints (14d): {', '.join(prints) if prints else 'none'}\n"
        "Grade the theme's activation now."
    )
    try:
        out = chat_json(_SYSTEM, prompt)
        grade = str(out.get("grade", "NONE")).upper()
        if grade not in ("GREAT", "GOOD", "NONE"):
            grade = "NONE"
        return {"grade": grade, "events": out.get("events", [])[:3], "note": str(out.get("note", ""))[:280]}
    except Exception as exc:
        log(f"why-now grading failed for {row['theme']}: {exc}")
        return None


def grade_radar(rows: list[dict], only: str | None = None) -> None:
    targets = [r for r in rows if r["status"] in ("ACTIVE", "WARM") and (only is None or r["theme"] == only)]
    for row in targets:
        row["why_now"] = grade_theme_activation(row)
        if row["why_now"]:
            log(f"why-now {row['theme']}: {row['why_now']['grade']} — {row['why_now']['note'][:80]}")