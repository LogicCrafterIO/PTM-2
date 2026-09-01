"""Deep dive hook and gatekeeping for the simple process.

The dive itself is PTM's engine, reused untouched (ptm_deepsearch run
through pipeline.run_deep_dive). Gatekeeping applies the starter pack's
questions WITHOUT price inputs:

1. WHY NOW    - the theme's radar status must be WARM/ACTIVE and the member
                must share (long) or diverge from (short) the theme lean.
2. EARLY/LATE - the print must still be ahead (>= 0 days) and the estimate
                move must be recent enough to still be actionable.
3. GETTING PAID (estimate-impact test, not a price target) - the dive's
                adapter verdict must carry at least one QUANTIFIED evidence
                item whose magnitude is material against the company's base
                (default: >= 3% on a core metric).
4. LISTENING  - theme breadth must not point against the idea.
"""

from __future__ import annotations

from datetime import date

from ptm.log import log

MIN_IMPACT_PCT = 3.0
MIN_DAYS_TO_PRINT = -1  # the print itself may be the catalyst; a passed print parks


def gate_member(member: dict, radar_row: dict, qual: dict | None, ref: date) -> dict:
    """Run the four gates for one shortlisted member.

    `qual` is the adapter verdict dict (evidence_for/against with impact_pct)
    or None when no dive ran yet — gates 3 then fail closed as 'dive pending'.
    """
    ticker = member["ticker"]
    lean = radar_row["lean"]
    divergent = (member.get("rev90") or 0) * radar_row["breadth"] < 0
    if "long_score" in member or "short_score" in member:
        wants_short = member.get("short_score", 0) >= member.get("long_score", 0)
    else:
        # raw snapshot without selection scores: the side is the divergence
        wants_short = divergent
    side = "short" if wants_short else "long"
    gates: list[dict] = []
    gates.append(
        {
            "gate": "why_now",
            "pass": radar_row["status"] in ("ACTIVE", "WARM") and aligned_ok(side, divergent, lean),
            "detail": f"theme {radar_row['status']} breadth {radar_row['breadth']:+.2f}, member rev90 {member.get('rev90')}, side {side}",
        }
    )
    days = member.get("days_to_print")
    gates.append(
        {
            "gate": "early_or_late",
            "pass": days is not None and days >= MIN_DAYS_TO_PRINT and days <= 60,
            "detail": f"print in {days} days" if days is not None else "no dated print",
        }
    )
    evidence, impact_ok, best = _impact_test(qual, ticker)
    gates.append(
        {
            "gate": "getting_paid",
            "pass": impact_ok,
            "detail": best or "no quantified evidence" if evidence else "dive pending",
        }
    )
    gates.append(
        {
            "gate": "listening",
            "pass": radar_row["status"] != "COLD",
            "detail": f"theme status {radar_row['status']}",
        }
    )
    passed = all(g["pass"] for g in gates)
    return {
        "ticker": ticker,
        "theme": radar_row["theme"],
        "side": side,
        "passed": passed,
        "gates": gates,
        "rev90": member.get("rev90"),
        "days_to_print": days,
        "earnings_date": member.get("earnings_date"),
        "lean": lean,
        "breadth": radar_row["breadth"],
    }


def aligned_ok(side: str, divergent: bool, lean: str) -> bool:
    if side == "short":
        return divergent or lean == "short"  # short the diverger, or short with the lean
    return not divergent  # longs must not fight their theme


def _impact_test(qual: dict | None, ticker: str) -> tuple[bool, bool, str]:
    """The getting-paid gate: a quantified, material magnitude vs the base."""
    if qual is None:
        return False, False, ""
    for item in qual.get("evidence_for", []) + qual.get("evidence_against", []):
        if not item.get("quantified") or item.get("impact_pct") is None:
            continue
        magnitude = abs(float(item["impact_pct"]))
        if magnitude >= MIN_IMPACT_PCT:
            return (
                True,
                True,
                f"{item.get('metric', 'metric')} {item['impact_pct']:+.1f}% on {item.get('impact_on', '?')}",
            )
    return True, False, "quantified evidence below the impact bar"


def gate_theme(selection: dict, radar_row: dict, quals: dict[str, dict | None], ref: date) -> dict:
    results = [gate_member(m, radar_row, quals.get(m["ticker"]), ref) for m in selection["long"] + selection["short"]]
    survivors = [r for r in results if r["passed"]]
    parked = [r for r in results if not r["passed"]]
    log(f"gate {selection['theme']}: {len(survivors)} idea(s), {len(parked)} parked")
    return {
        "theme": selection["theme"],
        "ideas": survivors,
        "parked": parked,
        "breadth_abs": abs(radar_row["breadth"]),
        "status": radar_row["status"],
    }