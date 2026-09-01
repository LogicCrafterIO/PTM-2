"""Ticker selection inside an activated theme — deterministic, no LLM.

The side comes from the NAME'S OWN revision direction, in either theme
direction: a theme waking DOWN is as tradable as one waking UP. Long
candidates have their own FY1 estimates rising (a rider in a rising theme,
or the share-gainer bucking a falling one); short candidates have them
falling (riding a falling theme, or the laggard inside a rising one). The
theme supplies the activation and the catalyst calendar; the name's own
estimates must confirm the side — the process never shorts rising estimates
or longs falling ones. The deep dive runs only on this shortlist.
"""

from __future__ import annotations

from ptm.log import log

from ptm.log import log


def _print_score(days: int | None) -> float:
    if days is None:
        return 0.0
    if 0 <= days <= 14:
        return 1.0
    if days <= 30:
        return 0.7
    if days <= 60:
        return 0.4
    return 0.0


def _durability(m: dict) -> float:
    cash, ni = m.get("cash"), m.get("net_income")
    score = 0.0
    if cash is not None and cash > 0:
        score += 0.5
    if ni is not None and ni > 0:
        score += 0.5
    return score


def _fragility(m: dict) -> float:
    cash, ni = m.get("cash"), m.get("net_income")
    score = 0.0
    if cash is not None and cash < 0:
        score += 0.5
    if ni is not None and ni < 0:
        score += 0.5
    return score


def _own(m: dict, direction: int) -> float:
    """The name's OWN 90d estimate direction, saturated at +/-5%.

    This is what makes falling themes symmetric: a member of a falling theme
    with falling estimates is a short candidate exactly the way a rising
    member of a rising theme is a long candidate, and a member going against
    its theme (up in a falling theme, down in a rising one) is scored on its
    OWN direction for the OPPOSITE side — never shorted for rising.
    """
    rev90 = m.get("rev90")
    if rev90 is None:
        return 0.0
    magnitude = min(abs(rev90) / 5.0, 1.0)
    return magnitude if rev90 * direction > 0 else 0.0


def _analyst(m: dict, direction: int) -> float:
    up, down = m.get("up30") or 0, m.get("down30") or 0
    if direction > 0:
        return min((up - down) / 3.0, 1.0)
    if direction < 0:
        return min((down - up) / 3.0, 1.0)
    return 0.0


def select_members(row: dict, per_side: int = 3) -> dict:
    """{long: [candidates], short: [candidates]} for one radar row.

    Hard eligibility before scoring: a long candidate MUST have its own
    estimates rising (> +0.5% over 90d, the same materiality the radar uses
    for breadth) and a short candidate falling (< -0.5%) — durability,
    timing and analyst breadth can rank a name, never flip its side.
    """
    longs: list[dict] = []
    shorts: list[dict] = []
    for m in row["members"]:
        if not m["covered"]:
            continue
        rev90 = m.get("rev90")
        entry = {**{k: m[k] for k in ("ticker", "rev90", "days_to_print", "earnings_date")},
                 "long_score": 0.0, "short_score": 0.0}
        if rev90 is not None and rev90 > 0.5:
            entry["long_score"] = round(
                0.35 * _own(m, +1) + 0.25 * _print_score(m["days_to_print"])
                + 0.20 * _durability(m) + 0.20 * _analyst(m, +1),
                3,
            )
            longs.append(entry)
        if rev90 is not None and rev90 < -0.5:
            entry["short_score"] = round(
                0.35 * _own(m, -1) + 0.25 * _print_score(m["days_to_print"])
                + 0.20 * _fragility(m) + 0.20 * _analyst(m, -1),
                3,
            )
            shorts.append(entry)
        if entry["long_score"] == 0.0 and entry["short_score"] == 0.0:
            continue  # flat estimates: no revision edge in either direction
    longs.sort(key=lambda e: -e["long_score"])
    shorts.sort(key=lambda e: -e["short_score"])
    out = {
        "theme": row["theme"],
        "lean": row["lean"],
        "status": row["status"],
        "breadth": row["breadth"],
        "bellwether": row["bellwether"],
        "long": [e for e in longs[:per_side] if e["long_score"] > 0.25],
        "short": [e for e in shorts[:per_side] if e["short_score"] > 0.25],
    }
    log(f"select {row['theme']}: long {[e['ticker'] for e in out['long']]} short {[e['ticker'] for e in out['short']]}")
    return out