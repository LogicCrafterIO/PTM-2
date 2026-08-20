"""Where analyst estimates are moving, and whether the filings back it up.

This is **revision momentum**, and the name matters: it is not a mispricing
claim. The book is ranked on the direction estimates are already travelling, in
the direction each trade needs, because estimate revisions under-react and tend
to continue. That is a well-documented effect and it is the empirically safest
thing to lean on here.

Two earlier designs were wrong and are worth recording so they are not rebuilt.

**Asking a model for an EPS surprise percentage.** It cannot back out a
consensus-implied growth rate and compare it to segment evidence; the estimates
clustered on 8.5/10/12/15 and every name returned "medium" confidence.

**Fading the analysts when filings disagreed.** This looked principled and was
not. A filing describes a quarter that has already CLOSED; analyst estimates
price the next four. When a company prints a strong quarter and analysts cut,
the likely explanation is that the analysts know something forward - an order
slowdown, a guidance cut on the call, end-market softness. Treating that
disagreement as a mispricing means fading the better-informed party, and it is a
contrarian bet against the documented momentum effect with nothing to support
the contrarian side.

So the filings are demoted to a **veto**. They do not generate the signal; they
can block a name whose own reported numbers point the opposite way to the
estimates being used to rank it. That is asymmetric caution - a risk control
rather than alpha - and it is defensible on those terms even though filing
evidence cannot establish that analysts are wrong.
"""

from __future__ import annotations

# There is no cap on revision size, deliberately. A ±30% winsor used to sit here
# and it was actively harmful: it did not remove the two arithmetic artefacts in
# the universe, it LAUNDERED them into plausible-looking numbers and put both in
# the book. ECHO's -1402% (base EPS -3.02, a sign flip) became a tidy -30%, and
# HTLD's +1369% (base EPS $0.013) became +30%. Meanwhile nine genuinely large
# revisions - PBF +160%, PARR +49%, SITM +42% - were flattened onto the same
# value, so the top of the ranking was decided by tiebreaks rather than by size.
#
# The artefact is handled where it originates instead: a percentage change is
# refused outright when its base is near zero or crosses zero, which is the rule
# ptm/ingest/company_research.py already applies to reported EPS changes. Real
# revisions then rank on their real size.
#
# A percentage is meaningless below this base, whatever the arithmetic says.
MIN_BASE_EPS = 0.20
# Below these a revision is indistinguishable from rounding.
FLAT_PCT = 1.0
FLAT_BREADTH = 1

DIRECTIONS = {"improving", "deteriorating", "mixed", "silent"}


def _compress(magnitude_pct: float) -> float:
    """Rank-safe transform of a revision size.

    Removing the winsor cap fixed the ties it created and immediately produced
    the opposite failure: CORT's genuine +347% revision scored ten times the
    next name and owned the entire ranking. Ties replaced by domination.

    So the raw percentage is kept for REPORTING - it is true and informative -
    and ranking runs on a log transform. Monotonic, so ordering is exactly
    preserved and no two different revisions ever tie; concave, so a 350% move
    ranks above a 35% one without being worth ten of it. Scaled so a 10% move
    scores about 10, which keeps the numbers readable next to the raw figure.
    """
    from math import log1p

    return round(log1p(max(0.0, magnitude_pct)) * 10.0 / log1p(10.0), 3)


def usable_base(current, prior) -> tuple[bool, str]:
    """Is a percentage change between these two EPS figures meaningful at all?

    Two ways it is not, both present in one real universe:

    * **The base crosses zero.** ECHO went from -3.02 to +39.34, which arithmetic
      renders as -1402%. A loss turning into a profit is real news and a
      percentage is the wrong way to say it.
    * **The base is a rounding error.** HTLD's 90-day-ago estimate was $0.013, so
      any move at all reads in the hundreds of percent.

    Refusing these is the same rule `_reported_changes` already applies to
    reported EPS. The alternative - capping the output - hides the artefact
    behind a plausible number instead of removing it.
    """
    if current is None or prior is None:
        return False, "no estimate history to measure against"
    current, prior = float(current), float(prior)
    if prior <= 0 or current <= 0:
        return False, f"estimate crosses zero ({prior:.3f} -> {current:.3f}); a percentage is meaningless"
    if abs(prior) < MIN_BASE_EPS:
        return False, f"base estimate of {prior:.3f} is too small for a percentage to mean anything"
    return True, ""


def consensus_drift(expectations: dict | None) -> dict:
    """How far and which way analysts have moved, from measured data only.

    Breadth (how many analysts moved up versus down) settles the direction. It
    is bounded, needs no division, and came back for 100% of names, where the
    percentage change is available for 98% and carries near-zero-base artefacts.
    The percentage then supplies the magnitude.
    """
    out = {
        "available": False,
        "direction": 0,
        "magnitude_pct": 0.0,
        "breadth": None,
        "change_90d_pct": None,
        "change_30d_pct": None,
        "why": "",
    }
    revisions = (expectations or {}).get("revisions") or {}
    if not revisions.get("available"):
        return out
    up, down = revisions.get("analysts_up_30d"), revisions.get("analysts_down_30d")
    breadth = None if up is None or down is None else int(up) - int(down)
    change_90 = revisions.get("change_90d_pct")
    change_30 = revisions.get("change_30d_pct")
    out.update(
        {
            "breadth": breadth,
            "change_90d_pct": None if change_90 is None else round(float(change_90), 2),
            "change_30d_pct": None if change_30 is None else round(float(change_30), 2),
        }
    )

    direction, reason = 0, ""
    if breadth is not None and abs(breadth) >= FLAT_BREADTH:
        direction = 1 if breadth > 0 else -1
        reason = f"{up} analysts up vs {down} down in 30 days"
    elif change_90 is not None and abs(float(change_90)) >= FLAT_PCT:
        direction = 1 if float(change_90) > 0 else -1
        reason = f"consensus {float(change_90):+.1f}% over 90 days"
    if direction == 0:
        out.update({"available": True, "why": "analysts have not moved"})
        return out

    ok, why_not = usable_base(revisions.get("eps_current"), revisions.get("eps_d90"))
    raw = change_90 if change_90 is not None else change_30
    if not ok or raw is None:
        # Direction still stands - the analyst head count does not depend on the
        # base - but the size cannot be measured, so it is not invented.
        out.update(
            {
                "available": True,
                "direction": direction,
                "magnitude_pct": None,
                "magnitude_unusable": why_not or "no percentage change available",
                "why": reason + f"; size not measurable: {why_not or 'no percentage available'}",
            }
        )
        return out
    pace = _acceleration(change_30, change_90, direction)
    out.update(
        {
            "available": True,
            "direction": direction,
            "magnitude_pct": round(abs(float(raw)), 2),
            "acceleration": pace["value"],
            "pace": pace["label"],
            "why": reason + (f", {pace['label']}" if pace["label"] else ""),
        }
    )
    return out


def _acceleration(change_30, change_90, direction: int) -> dict:
    """Is the revision still running, or did it stall a month ago?

    Both figures are "current versus N days ago", so the earlier 60 days can be
    backed out: (1+c90)/(1+c30) - 1. Comparing the recent monthly pace against
    that earlier pace says whether estimates are still being marked at the same
    rate going into the print, which is the strength question that matters.

    Two points is a thin basis and this is a coarse read, not a derivative. It
    is reported as a label rather than scaled into the score for that reason.
    """
    out = {"value": None, "label": ""}
    if change_30 is None or change_90 is None or direction == 0:
        return out
    recent = float(change_30)
    denom = 1.0 + recent / 100.0
    if abs(denom) < 1e-6:
        return out
    earlier_total = ((1.0 + float(change_90) / 100.0) / denom - 1.0) * 100.0
    recent_pace = recent  # one month
    earlier_pace = earlier_total / 2.0  # the preceding two months
    # Signed so positive always means "still moving the way it was moving".
    delta = (recent_pace - earlier_pace) * (1 if direction > 0 else -1)
    out["value"] = round(delta, 2)
    if abs(delta) < 0.5:
        out["label"] = "steady pace"
    elif delta > 0:
        out["label"] = "still accelerating"
    else:
        out["label"] = "pace has slowed"
    return out


def filing_direction(qual) -> int:
    """What the filings say, as +1 improving / -1 deteriorating / 0 unclear."""
    value = str(getattr(qual, "filing_direction", "") or "silent").strip().lower()
    return {"improving": 1, "deteriorating": -1}.get(value, 0)


def filings_veto(drift: dict, qual) -> str:
    """Do the company's own numbers point against the estimates being followed?

    Returns "" when there is nothing to say, otherwise a reason. This is a risk
    control and is framed as one: it does not assert the analysts are wrong,
    only that we are unwilling to follow a revision the company's own reported
    figures contradict.
    """
    fil = filing_direction(qual)
    con = int(drift.get("direction") or 0)
    if not drift.get("available") or con == 0 or fil == 0:
        return ""
    if fil == con:
        return ""
    moving = "raising" if con > 0 else "cutting"
    reads = "deteriorating" if fil < 0 else "improving"
    return (
        f"analysts are {moving} estimates while the company's own filings read {reads}; "
        "not following a revision its numbers contradict"
    )


# How much of the run is left, from the verdict's reading of the filings. The
# screen returns quantitative outliers, so a re-rating has usually started by the
# time a name arrives - which makes this the live question. `exhausted` is scored
# near zero rather than negative: a finished run is not a reason to take the
# other side, it is a reason not to take this one.
DURABILITY_WEIGHT = {
    "building": 1.2,
    "intact": 1.0,
    "fading": 0.5,
    "exhausted": 0.15,
    "unclear": 0.8,
}


def durability_weight(qual) -> float:
    return DURABILITY_WEIGHT.get(
        str(getattr(qual, "momentum_durability", "") or "unclear"), 0.8
    )


# Ceiling on the combined lift from durability, theme cohort and ISM. Each is
# defensible alone; multiplied out they reach 1.65x, and three correlated reads
# of "this theme is working" should not compound into near-double weight.
MAX_COMBINED_MULTIPLIER = 1.35
MIN_COMBINED_MULTIPLIER = 0.10


def momentum_edge(
    drift: dict,
    qual,
    side_is_long: bool,
    theme_corroboration: dict | None = None,
    ism_support: dict | None = None,
) -> dict:
    """Revision momentum signed FOR the trade, with the filings as a veto.

    A long wants estimates rising; a short wants them falling. The magnitude is
    the distance they have already travelled. Nothing here fades the analysts.
    """
    out = {
        "edge_pct": None,
        "consensus_direction": {1: "rising", -1: "falling"}.get(
            int(drift.get("direction") or 0), "flat"
        ),
        "filing_direction": {1: "improving", -1: "deteriorating"}.get(
            filing_direction(qual), "unclear"
        ),
        "magnitude_pct": drift.get("magnitude_pct"),
        "veto": "",
        "support": "",
        "why": "",
    }
    direction = int(drift.get("direction") or 0)
    if not drift.get("available"):
        out["why"] = "no analyst revision data"
        return out
    if direction == 0:
        out["why"] = "analysts have not moved, so there is no momentum to follow"
        return out
    if drift.get("magnitude_pct") is None:
        out["why"] = (
            f"estimates are {out['consensus_direction']} but the size is not measurable: "
            f"{drift.get('magnitude_unusable') or 'no percentage available'}"
        )
        return out

    helps = (direction > 0) if side_is_long else (direction < 0)
    magnitude = float(drift.get("magnitude_pct") or 0.0)
    raw = magnitude * (1.0 if helps else -1.0)
    scored = _compress(magnitude) * (1.0 if helps else -1.0)

    # Strength going into the print is the raw revision distance; how much is
    # LEFT is durability and theme corroboration. Both scale it rather than
    # replacing it, and both are modest multipliers - stacking correlated
    # momentum signals hard would let one driver count several times.
    durability = durability_weight(qual)
    theme = theme_corroboration or {}
    ism = ism_support or {}
    theme_mult = float(theme.get("multiplier") or 1.0)
    ism_mult = float(ism.get("multiplier") or 1.0)
    combined = max(
        MIN_COMBINED_MULTIPLIER,
        min(durability * theme_mult * ism_mult, MAX_COMBINED_MULTIPLIER),
    )
    out.update(
        {
            "raw_edge_pct": round(raw, 2),
            "score": round(scored, 3),
            "durability": str(getattr(qual, "momentum_durability", "") or "unclear"),
            "durability_weight": durability,
            "theme_multiplier": theme_mult,
            "ism_multiplier": ism_mult,
            "combined_multiplier": round(combined, 3),
            "themes": theme.get("themes") or [],
            "ism_notes": ism.get("notes") or [],
            "acceleration": drift.get("acceleration"),
            "pace": drift.get("pace"),
            # edge_pct is the reportable number; `score` is what the book ranks on.
            "edge_pct": round(raw * combined, 2),
            "edge_score": round(scored * combined, 3),
        }
    )
    out["veto"] = filings_veto(drift, qual)
    fil = filing_direction(qual)
    if fil != 0 and fil == direction:
        out["support"] = "the company's own filings point the same way"
    wanted = "rising" if side_is_long else "falling"
    parts = [
        f"estimates are {out['consensus_direction']} ({drift.get('why')}); this trade wants them {wanted}"
    ]
    if out["support"]:
        parts.append(out["support"])
    parts.append(f"the run reads {out['durability']}")
    if theme.get("why"):
        parts.append(theme["why"])
    if ism.get("why"):
        parts.append(ism["why"])
    out["why"] = "; ".join(parts)
    return out


def summary_line(payload: dict) -> str:
    """One line for the idea's markdown and the ranked table."""
    if payload.get("edge_pct") is None:
        return f"**Revision momentum:** none measurable — {payload.get('why') or 'no data'}."
    line = (
        f"**Revision momentum: {payload['edge_pct']:+.1f}%** — {payload.get('why')}. "
        "This follows the direction estimates are already moving rather than betting against "
        "it; it is momentum, not a claim that the market is mispriced."
    )
    if payload.get("veto"):
        line += f" **Vetoed:** {payload['veto']}."
    return line
