"""Ticker selection inside an activated theme — deterministic, no LLM.

Ranks a theme's members for BOTH directions. Long candidates align with the
theme's revision lean and carry the catalyst; short candidates are the
divergent names (revising against their own theme) with fragile books. The
deep dive runs only on the names that rank here — that is the whole saving.
"""

from __future__ import annotations

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


def _alignment(m: dict, lean: str) -> float:
    rev90 = m.get("rev90")
    if rev90 is None:
        return 0.0
    magnitude = min(abs(rev90) / 5.0, 1.0)  # a 5% 90d estimate move saturates
    if lean == "long":
        return magnitude if rev90 > 0 else 0.0
    if lean == "short":
        return magnitude if rev90 < 0 else 0.0
    return 0.0


def _against(m: dict, lean: str) -> float:
    rev90 = m.get("rev90")
    if rev90 is None:
        return 0.0
    magnitude = min(abs(rev90) / 5.0, 1.0)
    if lean == "long":
        return magnitude if rev90 < 0 else 0.0
    if lean == "short":
        return magnitude if rev90 > 0 else 0.0
    return 0.0


def _analyst(m: dict, direction: int) -> float:
    up, down = m.get("up30") or 0, m.get("down30") or 0
    if direction > 0:
        return min((up - down) / 3.0, 1.0)
    if direction < 0:
        return min((down - up) / 3.0, 1.0)
    return 0.0


def select_members(row: dict, per_side: int = 3) -> dict:
    """{long: [candidates], short: [candidates]} for one radar row."""
    lean = row["lean"]
    longs: list[dict] = []
    shorts: list[dict] = []
    for m in row["members"]:
        if not m["covered"]:
            continue
        long_score = round(
            0.35 * _alignment(m, lean) + 0.25 * _print_score(m["days_to_print"])
            + 0.20 * _durability(m) + 0.20 * _analyst(m, +1),
            3,
        )
        short_score = round(
            0.35 * _against(m, lean) + 0.25 * _print_score(m["days_to_print"])
            + 0.20 * _fragility(m) + 0.20 * _analyst(m, -1),
            3,
        )
        entry = {**{k: m[k] for k in ("ticker", "rev90", "days_to_print", "earnings_date")}, "long_score": long_score, "short_score": short_score}
        longs.append(entry)
        shorts.append(entry)
    longs.sort(key=lambda e: -e["long_score"])
    shorts.sort(key=lambda e: -e["short_score"])
    out = {
        "theme": row["theme"],
        "lean": lean,
        "status": row["status"],
        "breadth": row["breadth"],
        "bellwether": row["bellwether"],
        "long": [e for e in longs[:per_side] if e["long_score"] > 0.25],
        "short": [e for e in shorts[:per_side] if e["short_score"] > 0.25],
    }
    log(f"select {row['theme']}: long {[e['ticker'] for e in out['long']]} short {[e['ticker'] for e in out['short']]}")
    return out