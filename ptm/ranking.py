from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ptm.config import data_dir, ideas_dir, toml_settings
from ptm.io import write_json
from ptm.log import log
from ptm.models import Candidate, EvidenceItem, Side, TradeIdea

# Verdict-quality problems, as opposed to business risks. Only these weaken
# conviction: a red flag about tariffs is the analysis working, a red flag about
# the model contradicting itself is the analysis failing.
PROCESS_FLAGS = ("downgraded", "json_failed", "contradicts_evidence", "insufficient_evidence")


def long_key(c: Candidate) -> tuple:
    return (0 if c.mcap_ok else 1, -(c.ism_score or 0.0), -(c.eg1 or 0.0))


def short_key(c: Candidate) -> tuple:
    return (0 if c.mcap_ok else 1, -(c.ism_score or 0.0), (c.eg1 or 0.0))


# What a quantified reason moves, and how much that matters. Earnings accretion
# is the thing the screen actually trades, revenue is a step removed, margin a
# step further, and an unmeasurable claim earns only its base weight.
IMPACT_SCOPE = {"earnings": 1.0, "eps": 1.0, "revenue": 0.75, "sales": 0.75, "margin": 0.5}
# Above this the size of a single claim stops adding conviction: a 300% number
# off a near-zero base should not outweigh three solid 20% ones.
IMPACT_CAP_PCT = 30.0
# An unquantified but genuine reason is worth this much; a fully quantified
# earnings claim at or above the cap is worth BASE + MAX_BONUS.
BASE_WEIGHT = 1.0
MAX_BONUS = 3.0
# The priced-in penalty is deliberately gone. It docked 2.0 when a verdict said
# the market had already moved to the thesis, which encodes a mispricing
# worldview: that agreeing with the street is worthless. The process now follows
# revision momentum instead, where the market moving your way is CONFIRMATION.
# Penalising it would rank the book against its own primary signal. The
# priced_in field survives as commentary and moves nothing.


CONTRADICTS_SIDE_FLAG = "evidence_contradicts_side"


def _points_wrong_way(item: EvidenceItem, side: Side) -> bool:
    """Is this 'reason to do the trade' actually a reason not to?

    impact_pct is the change to impact_on, so the sign reads literally: a short
    whose reason is +216% earnings is citing growth as grounds for shorting, and
    a long whose reason is -30% revenue is citing contraction as grounds for
    paying a premium. Neither is evidence; each is the opposite of it.

    Rare and expensive. Across one full run, 3 of 106 quantified reasons were
    signed this way - but because magnitude is capped at 30%, a wrong-signed
    claim lands ON the cap and earns the MAXIMUM weight of 4.0. ARR reached the
    book on exactly one such item and nothing else.
    """
    if not item.quantified or item.impact_pct is None or item.impact_pct == 0:
        return False
    return item.impact_pct < 0 if side == Side.LONG else item.impact_pct > 0


def reconcile_sides(qual, side: Side) -> tuple[list[EvidenceItem], list[EvidenceItem], list[str]]:
    """Move wrong-signed reasons to the side they actually argue for.

    Moved rather than dropped: the model found a real reported figure and
    mislabelled which case it supports, so the fact belongs in the analysis -
    just on the other side of the ledger. Idempotent, so callers may apply it
    more than once.
    """
    if qual is None:
        return [], [], []
    keep, moved = [], []
    for item in qual.evidence_for:
        (moved if _points_wrong_way(item, side) else keep).append(item)
    notes = [
        f"{CONTRADICTS_SIDE_FLAG}: {i.claim[:80]} ({i.impact_pct:+.0f}% {i.impact_on})"
        for i in moved
    ]
    return keep, list(qual.evidence_against) + moved, notes


def evidence_weight(item: EvidenceItem) -> float:
    """How much one reason counts.

    A claim with no number from the filing scores BASE_WEIGHT - the same as the
    old count-based behaviour, so nothing is lost when a model declines to
    quantify. A claim the pack actually quantified scales up with its magnitude
    and with how directly it touches earnings.
    """
    if not item.claim.strip():
        return 0.0
    if not item.quantified or item.impact_pct is None:
        return BASE_WEIGHT
    scope = IMPACT_SCOPE.get((item.impact_on or "").strip().lower(), 0.25)
    magnitude = min(abs(float(item.impact_pct)), IMPACT_CAP_PCT) / IMPACT_CAP_PCT
    return BASE_WEIGHT + MAX_BONUS * magnitude * scope


def momentum(idea: TradeIdea, cohorts: dict | None = None, ism: dict | None = None) -> dict:
    """Revision momentum for one idea, with the filings veto. See ptm/drift.py.

    Named momentum rather than a gap or a mispricing because that is what it is:
    the direction analysts are already moving, followed rather than faded.

    `cohorts` is the cross-sectional theme reading from ptm/themes.py. When it is
    absent the per-idea value stored on `extra` is used instead, so the number in
    a report matches the one the book was built from.
    """
    from ptm.drift import consensus_drift, momentum_edge
    from ptm.themes import corroboration

    drift = consensus_drift(idea.extra.get("expectations"))
    themes = list((idea.qual.themes if idea.qual else None) or [])
    if cohorts is not None:
        theme_read = corroboration(themes, int(drift.get("direction") or 0), cohorts)
    else:
        theme_read = idea.extra.get("theme_corroboration") or {}
    if ism is not None:
        from ptm.themes import ism_support

        ism_read = ism_support(themes, ism)
    else:
        ism_read = idea.extra.get("ism_support") or {}
    return momentum_edge(
        drift, idea.qual, idea.candidate.side == Side.LONG, theme_read, ism_read
    )


def cohort_rows(ideas: list[TradeIdea]) -> list[dict]:
    """Per-idea input for the cross-sectional theme pass."""
    from ptm.drift import consensus_drift

    rows = []
    for idea in ideas:
        drift = consensus_drift(idea.extra.get("expectations"))
        rows.append(
            {
                "ticker": idea.candidate.ticker,
                "themes": list((idea.qual.themes if idea.qual else None) or []),
                "direction": int(drift.get("direction") or 0),
                "magnitude": drift.get("magnitude_pct"),
            }
        )
    return rows


def momentum_edge_pct(idea: TradeIdea) -> float | None:
    """The reportable edge: signed revision distance, scaled. For display."""
    return momentum(idea).get("edge_pct")


def momentum_score(idea: TradeIdea) -> float | None:
    """What the book actually ranks on: the log-compressed edge.

    Separate from `momentum_edge_pct` on purpose. The percentage is the honest
    number to show; ranking on it let one 347% revision out-score the rest of
    the book ten to one. See ptm/drift._compress.
    """
    return momentum(idea).get("edge_score")


def theme_score(idea: TradeIdea) -> float:
    """How thematically exposed this name is, from its own filings.

    A tiebreak, not a thesis. Exposure says the company talks about a theme, not
    that the exposure is material or unpriced - so it orders names that are
    otherwise equal rather than promoting a weak idea over a strong one.
    """
    qual = idea.qual
    if qual is None or not getattr(qual, "themes", None):
        return 0.0
    total = 0.0
    for label in qual.themes:
        # Labels arrive as "AI and data centre (52)".
        try:
            total += float(str(label).rsplit("(", 1)[1].rstrip(")"))
        except (IndexError, ValueError):
            total += 1.0
    # Compressed hard: 52 mentions is not 52 times better than 1.
    return round(min(total, 60.0) / 60.0, 4)


def conviction_detail(qual, side: Side = Side.LONG) -> dict:
    """The conviction score with its full arithmetic, for the idea's JSON.

    Written onto every idea so the number can be checked rather than trusted:
    each reason appears with its magnitude, what that magnitude moves, and the
    weight it earned.
    """
    if qual is None:
        return {"score": 0.0, "for": [], "against": [], "penalties": []}

    def rows(items) -> list[dict]:
        return [
            {
                "claim": i.claim,
                "metric": i.metric or None,
                "impact_pct": i.impact_pct,
                "impact_on": i.impact_on if i.quantified else None,
                "quantified": i.quantified,
                "weight": round(evidence_weight(i), 3),
            }
            for i in items
        ]

    for_items, against_items, contradictions = reconcile_sides(qual, side)
    for_rows, against_rows = rows(for_items), rows(against_items)
    penalties = [
        flag
        for flag in qual.red_flags
        if any(marker in flag for marker in PROCESS_FLAGS)
    ] + contradictions
    score = sum(r["weight"] for r in for_rows) - sum(r["weight"] for r in against_rows)
    if [p for p in penalties if any(m in p for m in PROCESS_FLAGS)]:
        score -= BASE_WEIGHT
    return {
        "score": round(score, 4),
        "priced_in": str(getattr(qual, "priced_in", "unknown") or "unknown"),
        "market_expectation": str(getattr(qual, "market_expectation", "") or ""),
        "deviation": str(getattr(qual, "deviation", "") or ""),
        "for_total": round(sum(r["weight"] for r in for_rows), 3),
        "against_total": round(sum(r["weight"] for r in against_rows), 3),
        "quantified_items": sum(1 for r in for_rows + against_rows if r["quantified"]),
        "for": for_rows,
        "against": against_rows,
        "penalties": penalties,
        "scale": (
            f"unquantified reason = {BASE_WEIGHT}; a quantified earnings claim at or above "
            f"{IMPACT_CAP_PCT:.0f}% = {BASE_WEIGHT + MAX_BONUS}. Scope weights: "
            + ", ".join(f"{k} {v}" for k, v in IMPACT_SCOPE.items())
        ),
    }


def conviction(idea: TradeIdea) -> float:
    """How strongly the qualitative pass backed this idea.

    Net weight of the evidence the verdict enumerated, docked for process
    failures. Only meaningful among ideas that already passed the gate - every
    one has supports_outlier True, so this separates "the evidence was
    overwhelming" from "it just about held up".

    Weighted rather than counted: counting made "backlog up 22%" and "management
    sounds confident" identical, so a name with four vague reasons outranked one
    with two quantified ones. See evidence_weight.
    """
    qual = idea.qual
    if qual is None:
        return 0.0
    for_items, against_items, _ = reconcile_sides(qual, idea.candidate.side)
    score = sum(evidence_weight(i) for i in for_items)
    score -= sum(evidence_weight(i) for i in against_items)
    if any(marker in flag for flag in qual.red_flags for marker in PROCESS_FLAGS):
        score -= BASE_WEIGHT
    return round(score, 4)


def ordered_ideas(ideas: list[TradeIdea]) -> list[TradeIdea]:
    """Book selection order: size band, ISM tilt, conviction, then eg1.

    Conviction ranks AHEAD of earnings growth, and that is deliberate rather
    than a tiebreak. By this point every name has already cleared the P/E
    outlier screen, fits a process EG case, and passed the qualitative gate, so
    eg1 is no longer separating good ideas from bad - and worse, it is not
    comparable across cases. Measured on one run's 98 ready longs:

        decel_still_above   eg1 median +0.60   (range +0.19 .. +5.32)
        turnaround          eg1 median -0.39   (range -0.79 .. -0.01)

    A turnaround long has negative eg1 *by definition*. Sorting on eg1 therefore
    buried all 22 turnarounds beneath every decel-still-above name for reasons
    that say nothing about idea quality. Conviction - the net evidence the
    verdict actually enumerated - is the better discriminator among names the
    screen has already declared outliers, and eg1 still orders within each
    conviction level.

    Deliberately not used for RANKING.md, which is written before any research
    exists and so has no conviction to rank on. That file remains the pure quant
    record of what the screen said.
    """
    if not bool((toml_settings().get("filters") or {}).get("qual_rank", True)):
        return list(ideas)

    def key(idea: TradeIdea) -> tuple:
        cand = idea.candidate
        eg1 = cand.eg1 or 0.0
        # QUALITATIVE factors order the book. The quant screen is a FILTER: by
        # this point every name is already a P/E outlier that fits an EG case,
        # clears the relative-PEG ceiling and passed the gate, so re-sorting on
        # those same measures merely restates the filter.
        #
        # Revision momentum leads. The process follows the direction estimates
        # are already travelling rather than trying to identify a mispricing -
        # mispricings are close to unidentifiable from filings, and an earlier
        # design that faded analysts on backward-looking evidence was betting
        # against a documented momentum effect. Let the market help.
        edge = momentum_score(idea)
        return (
            # 1. Are estimates moving this trade's way, and how hard? Ranked on
            #    the compressed score, not the raw percentage - see momentum_score.
            -(edge if edge is not None else -999.0),
            # 2. How well evidenced is the case at all?
            -conviction(idea),
            # 3. Thematic exposure, as a tiebreak between equals.
            -theme_score(idea),
            # 4. Sector tilt, then growth - both quant, both last.
            -(cand.ism_score or 0.0),
            -eg1 if cand.side == Side.LONG else eg1,
        )

    return sorted(ideas, key=key)


def rank_reason(c: Candidate) -> str:
    if c.pe1 is not None and c.sector_pe1 is not None:
        pe_bit = f"PE {c.pe1:.1f} vs sector {c.sector_pe1:.1f}"
    elif c.pe1 is not None:
        pe_bit = f"PE {c.pe1:.1f}"
    else:
        pe_bit = "PE n/a"
    ism_bit = f"ISM {c.ism_score:+.2f}"
    if c.ism_why:
        ism_bit += f" ({c.ism_why[:80]})"
    mcap_bit = "mcap in band" if c.mcap_ok else (c.mcap_warning or "mcap outside band")
    eg = c.eg_case or "unknown"
    return f"{pe_bit}; {ism_bit}; EG case {eg}; {mcap_bit}"


def ordered_candidates(candidates: list[Candidate]) -> list[Candidate]:
    longs = sorted([c for c in candidates if c.side == Side.LONG], key=long_key)
    shorts = sorted([c for c in candidates if c.side == Side.SHORT], key=short_key)
    return longs + shorts


def ranking_rows(candidates: list[Candidate]) -> list[dict]:
    longs = sorted([c for c in candidates if c.side == Side.LONG], key=long_key)
    shorts = sorted([c for c in candidates if c.side == Side.SHORT], key=short_key)
    rows: list[dict] = []
    for i, cand in enumerate(longs, start=1):
        why = rank_reason(cand)
        rows.append(
            {
                "side": "long",
                "rank": i,
                "of": len(longs),
                "ticker": cand.ticker,
                "name": cand.name,
                "why": f"Long #{i}/{len(longs)}: {why}",
                "ism_score": cand.ism_score,
                "eg_case": cand.eg_case,
                "mcap_ok": cand.mcap_ok,
            }
        )
    for i, cand in enumerate(shorts, start=1):
        why = rank_reason(cand)
        rows.append(
            {
                "side": "short",
                "rank": i,
                "of": len(shorts),
                "ticker": cand.ticker,
                "name": cand.name,
                "why": f"Short #{i}/{len(shorts)}: {why}",
                "ism_score": cand.ism_score,
                "eg_case": cand.eg_case,
                "mcap_ok": cand.mcap_ok,
            }
        )
    return rows


def write_ranking(candidates: list[Candidate], day: str | None = None) -> Path:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = ranking_rows(candidates)
    payload = {"as_of": datetime.now(timezone.utc).isoformat(), "rows": rows}
    json_path = data_dir("curated", "ranking.json")
    write_json(json_path, payload)
    lines = ["# PE candidate ranking", "", f"As of: {payload['as_of']}", ""]
    longs = [r for r in rows if r["side"] == "long"]
    shorts = [r for r in rows if r["side"] == "short"]
    lines.append(f"## Longs ({len(longs)})")
    lines.append("")
    for row in longs:
        lines.append(f"- **{row['ticker']}** — {row['why']}")
    lines += ["", f"## Shorts ({len(shorts)})", ""]
    for row in shorts:
        lines.append(f"- **{row['ticker']}** — {row['why']}")
    md_path = ideas_dir(day, "RANKING.md")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"ranking: {len(longs)} longs / {len(shorts)} shorts → {md_path.name}")
    return md_path
