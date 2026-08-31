"""Map a deep dive (``DeepResult``) onto the pipeline's ``QualResult``.

The idea pipeline's qualitative gate used to read one EDGAR research pack and
ask a model whether the operating evidence explains the quantitative outlier.
That pass now runs the full deep dive instead — web-grounded research, drivers,
a structured bull/bear debate and a synthesised stance — and this module turns
that dossier into the structured verdict the gates and the book ranking
already consume:

* ``supports_outlier`` — the same side-aware boolean as before. For a LONG the
  evidence must justify paying the premium; for a SHORT it must show the
  discount is deserved. The dive's stance maps cleanly: a constructive read
  supports a long, a cautious read supports a short, a balanced read supports
  neither side's trade, and an unclear read defers rather than blocks.
* ``evidence_for`` / ``evidence_against`` — the sized, sourced claims the
  conviction score weighs. ``quantified`` survives only when the magnitude
  appears verbatim in the dive's own text (see ``_verify_quantified``), so the
  honesty rule the old verdict enforced by prompt is enforced here by check.
* ``filing_direction`` / ``momentum_durability`` — the classifications the
  filings veto and the durability weight read.

One verdict-model call per name does this mapping; when no LLM is available a
deterministic fallback maps the stance and the debate's own text directly, so
a dive never comes back unusable.
"""

from __future__ import annotations

import re

from ptm.deepsearch.models import DebateRound, DeepResult, Thesis
from ptm.llm import JSON_HINT, _clip, chat_json, llm_available, verdict_model
from ptm.log import log
from ptm.config import toml_settings
from ptm.models import Candidate, DriverScore, EvidenceItem, QualResult, Side
from ptm.themes import labels as theme_labels

# Stance → whether it supports the trade, per side. A "balanced" dive reads
# genuinely two-sided, which supports NEITHER paying the premium nor pressing
# the discount, so both sides treat it as a deny; "unclear" defers (None)
# rather than blocking. This mirrors what the adapter prompt instructs.
_LONG_STANCE = {"constructive": True, "cautious": False, "balanced": False}
_SHORT_STANCE = {"cautious": True, "constructive": False, "balanced": False}
_STANCE_DIRECTION = {
    "constructive": "improving",
    "cautious": "deteriorating",
    "balanced": "mixed",
}
_CONFIDENCES = {"high", "medium", "low"}

# Every percentage figure that literally appears in a text. impact_pct is by
# contract a period-over-period change measured in percent, so only those can
# verify a claimed magnitude.
_PCT_FIGURE_RE = re.compile(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*(?:%|percent|pct\b|percentage)")


def stance_supports(stance: str, side: Side) -> bool | None:
    """Does the dive's stance support THIS side's trade? None = deferred."""
    table = _LONG_STANCE if side == Side.LONG else _SHORT_STANCE
    return table.get(str(stance or "").strip().lower())


def _figures_in(text: str) -> list[float]:
    """Every percent-shaped number in the text, as floats."""
    out: list[float] = []
    for match in _PCT_FIGURE_RE.finditer(text or ""):
        try:
            out.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return out


# --- Quantitative qual scoring ------------------------------------------------
# The stance alone is a label; this layer makes the qualitative call measurable.
# Each debate driver is scored -2..+2 (sign = which side won the round, bull
# positive; magnitude = how decisively), then aggregated with FIXED weights.
# The weights follow where the dives actually argue: the operating case
# (fundamentals), its dated events (catalysts), its durability (competitive)
# and its hazards (risk) are the evidence the research can ground. Valuation
# stays a pillar but demoted — the P/E outlier that CREATED the candidate is
# the screen's call, and the adapter bans screen-valuation evidence from the
# qual verdict, so a dive rarely produces an independent multiple argument.
# Any absent category's weight is renormalized away (see aggregate_scores), so
# these fractions distribute influence WITHIN a dive, nothing punishes a dive
# for skipping a pillar. Weights are code, not the model's choice — the same
# debate always produces the same numbers.
CATEGORY_WEIGHTS = {
    "valuation": 0.12,
    "fundamentals": 0.36,
    "catalysts": 0.22,
    "competitive": 0.18,
    "risk": 0.12,
}
_CONF_MULT = {"high": 1.0, "medium": 0.7, "low": 0.45}
# Drivers the synthesis scored but whose debate round is missing still need a
# verdict label for the scorecard; direction stands in.
_DIRECTION_SIDE = {"tailwind": "bull", "headwind": "bear", "neutral": "tie"}
# The dive's stance as a point on the same -2..+2 scale, used only to flag
# when the driver-level evidence and the synthesised label disagree.
_STANCE_SCORE_PROXY = {"constructive": 1.7, "cautious": -1.7, "balanced": 0.0, "unclear": 0.0}

_CATEGORY_KEYWORDS = (
    ("valuation", ("valuation", "peg", "multiple", "premium", "discount", "overpriced", "underpriced", "re-rat", "rerat", "cheap")),
    ("catalysts", ("catalyst", "inflection", "approval", "launch", "contract win", "guidance", "buyback", "spin-off")),
    ("competitive", ("moat", "market share", "competitor", "competition", "rival", "entrant", "share loss", "share gain")),
    ("risk", ("risk", "lawsuit", "concentration", "churn", "regulat", "leverage", "covenant", "dilution")),
)


def score_supports(s: float | None, side: Side, threshold: float) -> bool | None:
    """Does the aggregated evidence score support THIS side's trade?

    Long needs the evidence reading constructive (S > 0); short needs it
    reading cautious (S < 0). |S| inside the threshold is the balanced band —
    genuinely two-sided evidence supports neither trade, and None defers.
    """
    if s is None:
        return None
    if abs(s) < threshold:
        return None
    return s >= threshold if side == Side.LONG else s <= -threshold


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _driver_confidence_mult(thesis: Thesis, driver_name: str) -> tuple[float, str]:
    """The dive's own confidence for a named driver, as a 0..1 multiplier."""
    name = _norm(driver_name)
    for d in thesis.drivers:
        d_name = _norm(d.name)
        if d_name and (d_name in name or name in d_name):
            return _CONF_MULT.get(d.confidence, 0.7), str(d.confidence or "medium")
    return 0.7, "unknown"


def _classify_category(text: str) -> str:
    lowered = _norm(text)
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(k in lowered for k in keywords):
            return category
    return "fundamentals"


def _row_category(category: str, driver_name: str, evidence: str) -> str:
    """The synthesis names the pillar; a missing or unknown label is derived
    from the driver's own words rather than silently zero-weighted."""
    if category in CATEGORY_WEIGHTS:
        return category
    return _classify_category(f"{driver_name} {evidence}")


def driver_rows(thesis: Thesis | None) -> list["DriverScore"]:
    """The dive's driver scores as one auditable row per driver.

    Single source of truth: the SYNTHESIS pass scored each driver while
    choosing the stance (Driver.score / category / score_why) — the score is
    reasoned there, in the same weighing that produced the thesis. A driver
    without a synthesis score (dives cached before scoring moved into the
    synthesis, or a model that skipped it) falls back to its debate round's
    verdict_side, with the round's verdict text as the reasoning. The weights
    are applied here, in code, identically for both paths.
    """
    if thesis is None:
        return []
    rounds_by_name: dict[str, "DebateRound"] = {_norm(r.driver): r for r in thesis.debate[:6]}
    rows: list[dict] = []
    for d in thesis.drivers[:5]:
        entry = rounds_by_name.get(_norm(d.name))
        score = d.score
        why = d.score_why
        verdict_side = ""
        if score is None and entry is not None:
            side = (entry.verdict_side or "").strip().lower()
            # Base magnitude only; confidence applies once, in the contribution.
            score = 0.0 if side in ("tie", "", "unresolved") else (1.5 if side == "bull" else -1.5)
        if entry is not None:
            verdict_side = (entry.verdict_side or "").strip().lower() or "tie"
            if not why:
                why = entry.verdict
        else:
            verdict_side = _DIRECTION_SIDE.get((d.direction or "").strip().lower(), "tie")
            if not why:
                why = d.evidence
        if score is None:
            continue
        mult, conf = _driver_confidence_mult(thesis, d.name)
        rows.append(
            {
                "driver": str(d.name)[:100],
                "category": _row_category(str(d.category or "").strip().lower(), d.name, d.evidence),
                "score": round(max(-2.0, min(2.0, float(score))), 2),
                "verdict_side": verdict_side,
                "confidence": conf,
                "mult": mult,
                "why": _clip(why, 240),
            }
        )
    if not rows:
        return []
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    out: list[DriverScore] = []
    for r in rows:
        weight = CATEGORY_WEIGHTS.get(r["category"], 0.0) / max(1, counts[r["category"]])
        out.append(
            DriverScore(
                driver=r["driver"],
                category=r["category"],
                score=r["score"],
                verdict_side=r["verdict_side"],
                confidence=r["confidence"],
                weight=round(weight, 4),
                contribution=round(r["score"] * r["mult"] * weight, 4),
                why=r["why"],
            )
        )
    return out


def aggregate_scores(rows: list[DriverScore]) -> dict:
    """Deterministic S, sub-scores and the mirrored 0-10 long/short pair.

    S = sum of contributions RENORMALIZED over the categories the dive actually
    scored, still in [-2, +2]. A dive that never surfaces a valuation or
    competitive argument must not have 42% of the intended weight silently
    vanish from its score — that compressed every S toward zero and made the
    decision bar (|S| >= threshold) harder to clear the thinner the dive's
    category mix was. Dividing by the present categories' weight keeps the
    bar meaning the same thing for every dive. Absent categories still read
    None in the per-category sub-scores — genuinely missing, not a fake 5 —
    and the scorecard records the renormalization so nothing hides.
    """
    if not rows:
        return {"s": None, "long": None, "short": None, **{c: None for c in CATEGORY_WEIGHTS}}
    present = {r.category for r in rows if r.category in CATEGORY_WEIGHTS}
    present_weight = sum(CATEGORY_WEIGHTS[c] for c in present)
    raw = sum(r.contribution for r in rows)
    s = round(raw / present_weight, 3) if present_weight > 0 else 0.0
    subs: dict[str, float | None] = {}
    for category, weight in CATEGORY_WEIGHTS.items():
        in_cat = [r for r in rows if r.category == category]
        if not in_cat:
            subs[category] = None
            continue
        s_cat = sum(r.contribution for r in in_cat)
        subs[category] = round(max(0.0, min(10.0, ((s_cat / weight) + 2.0) / 4.0 * 10.0)), 1)
    long_score = round(max(0.0, min(10.0, (s + 2.0) / 4.0 * 10.0)), 1)
    short_score = round(max(0.0, min(10.0, (2.0 - s) / 4.0 * 10.0)), 1)
    return {
        "s": s,
        "long": long_score,
        "short": short_score,
        # Fraction of the fixed weight mix the dive's drivers actually covered;
        # below 1.0 means the score was renormalized over present categories.
        "weight_covered": round(present_weight, 2),
        "valuation": subs["valuation"],
        "fundamentals": subs["fundamentals"],
        "catalysts": subs["catalysts"],
        "competitive": subs["competitive"],
        "risk": subs["risk"],
    }


def category_weights() -> dict[str, float]:
    """The fixed category weight mix, for rendering and any other consumer."""
    return dict(CATEGORY_WEIGHTS)


def _score_threshold() -> float:
    try:
        return float((toml_settings().get("qualitative_bar") or {}).get("score_support_threshold", 0.6))
    except Exception:
        return 0.6


def _resolved_supports(
    score_s: float | None,
    stance: str,
    side: Side,
) -> tuple[bool | None, list[str]]:
    """Score-first support resolution; the stance label stands in the balanced band.

    Decisive debate (|S| >= threshold) sets the verdict outright — visible with
    an override flag when it contradicts the synthesised stance — while a
    genuinely two-sided debate defers to the dive's stance, exactly as the old
    side-aware mapping behaved. |S - stance_proxy| beyond a gap is flagged so a
    synthesis that ignores its own debate is visible.
    """
    stance_val = stance_supports(stance, side)
    if score_s is None:
        return stance_val, []
    flags: list[str] = []
    proxy = _STANCE_SCORE_PROXY.get((stance or "").strip().lower())
    sup = score_supports(score_s, side, _score_threshold())
    if sup is not None and stance_val is not None and sup != stance_val:
        flags.append(f"verdict_score_overrides_stance (S={score_s:+.2f} vs dive stance {stance})")
    if proxy is not None and abs(score_s - proxy) >= 1.2:
        flags.append(f"score_disagrees_with_dive_stance (S={score_s:+.2f} vs {stance or 'unclear'})")
    return (sup if sup is not None else stance_val), flags


def _apply_scores(qual: QualResult, rows: list[DriverScore]) -> None:
    """Fill the QualResult score fields from the aggregated debate."""
    agg = aggregate_scores(rows)
    qual.score_s = agg["s"]
    qual.score_long = agg["long"]
    qual.score_short = agg["short"]
    qual.score_valuation = agg["valuation"]
    qual.score_fundamentals = agg["fundamentals"]
    qual.score_catalysts = agg["catalysts"]
    qual.score_competitive = agg["competitive"]
    qual.score_risk = agg["risk"]
    qual.driver_scores = rows


def _verify_quantified(items: list[EvidenceItem], evidence_text: str) -> tuple[list[EvidenceItem], int]:
    """Drop quantified flags whose magnitude never appears in the dive.

    The adapter asks the model to mark a claim quantified only when the dive's
    own text carries the number. Enforcing that check here is the difference
    between instructing honesty and guaranteeing it: a quantified item feeds
    both the conviction score and the ``min_quantified_for`` gate, so an
    invented magnitude must never survive. The claim itself is kept, with
    ``quantified=False``.
    """
    figures = _figures_in(evidence_text)
    out: list[EvidenceItem] = []
    stripped = 0
    for item in items:
        if item.quantified and item.impact_pct is not None:
            magnitude = abs(float(item.impact_pct))
            if any(abs(magnitude - abs(fig)) < 0.15 for fig in figures):
                out.append(item)
                continue
            stripped += 1
            out.append(
                EvidenceItem(
                    claim=item.claim,
                    metric=item.metric,
                    impact_pct=None,
                    impact_on="none",
                    quantified=False,
                )
            )
            continue
        out.append(item)
    return out, stripped


def _findings_block(result: DeepResult, limit: int = 12000) -> str:
    findings = [f.model_dump() for f in (result.research.findings if result.research else [])]
    lines = []
    for i, f in enumerate(findings, 1):
        src = f.get("source") or {}
        dated = f" (dated {f.get('dated')})" if f.get("dated") else ""
        via = f" — {src.get('title') or src.get('url') or ''}" if src else ""
        lines.append(f"[{i}] {f.get('claim') or ''}{dated}{via}")
    return "\n".join(lines)[:limit]


def _debate_block(thesis: Thesis) -> str:
    rows = []
    for r in thesis.debate[:5]:
        rows.append(
            f"DRIVER {r.driver}: bull said \"{r.bull[:220]}\"; bear said \"{r.bear[:220]}\"; "
            f"verdict {r.verdict_side or 'unresolved'} — {r.verdict[:240]}"
        )
    return "\n".join(rows)


ADAPTER_SYSTEM = (
    "You are doing PTM qualitative processing on ONE name. A good company is not automatically a "
    "good trade, and a bad company is not automatically a good short. "
    "You are given a quantitative outlier (a P/E far from its sector) AND a completed deep research "
    "dive on the company: web-grounded, source-cited findings, a structured bull-vs-bear debate per "
    "driver, and a synthesised stance. Say whether the evidence in THAT DIVE explains the gap.\n"
    "For a LONG (premium multiple): answer true when the dive shows growth, acceleration, backlog, "
    "pricing power or a credible plan that could grow into the multiple.\n"
    "For a SHORT (discount multiple): answer true when the dive shows the discount is DESERVED — "
    "declining volumes, shrinking margins, lost share, one-off EPS, structural decline or no "
    "credible plan. A cautious stance on the company is CONFIRMING evidence for a short, not a "
    "reason to reject it.\n"
    "The dive's own stance informs but does not decide your answer: weigh the evidence_for and "
    "evidence_against you list, and note where the debate verdicts landed. A dive that reads "
    "genuinely two-sided (balanced) supports NEITHER paying a premium NOR pressing a discount.\n"
    "Evidence must come from the dive — its findings, drivers, debate rounds, bull/bear points — "
    "never from the quantitative screen. Never cite consensus FY1/FY2 EPS growth, P/E, PEG, "
    "relative valuation or the EG case as evidence; those created the candidate and cannot "
    "independently confirm it. "
    "Every evidence item is an object: {claim, metric, impact_pct, impact_on, quantified}. "
    "impact_pct is a CHANGE measured in percent — growth, decline or accretion. A standing level "
    "or ratio is a useful claim but not a change, so leave impact_pct null for it. "
    "Set quantified=true ONLY when that exact percentage figure appears in the dive text you are "
    "shown; magnitudes are verified mechanically afterwards and invented ones are stripped, which "
    "costs the name its conviction. A claim you can cite precisely outranks one you cannot. "
    "impact_on must be earnings, revenue, margin or none. "
    + JSON_HINT
)

_DIRECTION_RULE = (
    "Set filing_direction to what the dive (filings grounding plus web evidence) says about where "
    "THIS company's earnings are heading: improving | deteriorating | mixed | silent. Judge the "
    "company, NOT the trade; a short whose evidence is improving must be reported as improving. "
    "Set direction_basis to the specific figures or findings behind the call. "
)

_DURABILITY_RULE = (
    "Set momentum_durability from the dive: building | intact | fading | exhausted | unclear. "
    "The screen returns outliers, so any re-rating has usually already started; the question is "
    "how much is left. Guidance raised again, backlog still building and orders accelerating read "
    "as building; guidance merely reaffirmed, harder comparatives and a lapping one-off read as "
    "fading. Set durability_basis to the specific evidence. "
)


def _candidate_context(candidate: Candidate) -> str:
    ratio = ""
    if candidate.pe1 and candidate.sector_pe1:
        ratio = f" ({candidate.pe1 / candidate.sector_pe1:.1f}x sector)"
    industry_bit = ""
    if candidate.pe1 and candidate.industry_pe1:
        industry_bit = f" vs industry {candidate.industry_pe1} ({candidate.pe1 / candidate.industry_pe1:.1f}x)"
    eg1_bit = (
        f", which is {candidate.eg1 * 100:+.1f}% on last year's {candidate.eps0}"
        if candidate.eg1 is not None
        else ""
    )
    ask = (
        "does the evidence justify PAYING this premium?"
        if candidate.side == Side.LONG
        else "does the evidence show this discount is DESERVED?"
    )
    return (
        f"Side={candidate.side.value}. P/E {candidate.pe1} vs sector {candidate.sector_pe1}{ratio}"
        f"{industry_bit}. EG case={candidate.eg_case}.\n"
        f"CONSENSUS THE MARKET IS HOLDING: FY1 EPS {candidate.eps1}{eg1_bit}.\n"
        f"Question: {ask}"
    )


def _adapter_call(result: DeepResult, candidate: Candidate, evidence_text: str, used_out: list[str]) -> dict:
    thesis = result.thesis
    dive_summary = (
        f"Dive stance: {thesis.stance} (confidence {thesis.confidence} — {thesis.confidence_why})\n"
        f"Thesis: {thesis.thesis}\n\n"
        f"Drivers:\n"
        + "\n".join(
            f"- {d.name} [{d.direction}, {d.confidence}]: {d.evidence[:220]}" for d in thesis.drivers[:5]
        )
        + "\n\nDebate rounds:\n" + _debate_block(thesis)
        + "\n\nBull points:\n"
        + "\n".join(f"- ({b.strength}) {b.point}: {b.evidence[:200]}" for b in thesis.bull_case[:6])
        + "\n\nBear points:\n"
        + "\n".join(f"- ({b.severity}) {b.point}: {b.evidence[:200]}" for b in thesis.bear_case[:6])
        + (
            "\n\nFalsifiers the dive named: " + "; ".join(thesis.falsifiers[:6])
            if thesis.falsifiers
            else ""
        )
    )
    user = (
        "Return JSON keys, IN THIS ORDER — the first four decide whether this idea is used at all: "
        "filing_direction (improving|deteriorating|mixed|silent), direction_basis (string), "
        "momentum_durability (building|intact|fading|exhausted|unclear), durability_basis (string), "
        "supports_outlier (bool), why (string, 2-4 sentences), denial_reason (string), "
        "evidence_for (array of {claim, metric, impact_pct, impact_on, quantified}, at most 4), "
        "evidence_against (same shape, at most 4), kpis (string[3-6], forward operating drivers like "
        "backlog, orders, utilisation, pricing, guidance — not statement lines), "
        "operating_plan (string; one concrete forward action, empty for a mission statement).\n"
        f"{_candidate_context(candidate)}\n\n"
        f"Deep dive on the name:\n{dive_summary[:12000]}\n\n"
        f"Source-cited findings gathered by the dive (numbered):\n{_findings_block(result)}\n"
    )
    return chat_json(_adapter_system_text(), user, model=verdict_model(), used_out=used_out)


def _adapter_system_text() -> str:
    return ADAPTER_SYSTEM + _DIRECTION_RULE + _DURABILITY_RULE


def _evidence_items(raw: object, from_llm: bool = True) -> list[EvidenceItem]:
    """Parse adapter evidence, tolerating bare strings (same shape as llm.py's)."""
    items: list[EvidenceItem] = []
    for entry in (raw or [])[:4]:
        if isinstance(entry, dict):
            claim = _clip(entry.get("claim") or entry.get("evidence") or entry.get("reason"), 240)
            if not claim:
                continue
            impact = entry.get("impact_pct")
            try:
                impact = None if impact in (None, "", "null") else float(impact)
            except (TypeError, ValueError):
                impact = None
            if impact is not None and abs(impact) > 500.0:
                impact = None
            quantified = bool(entry.get("quantified")) and impact is not None
            items.append(
                EvidenceItem(
                    claim=claim,
                    metric=_clip(entry.get("metric"), 80),
                    impact_pct=impact if quantified else None,
                    impact_on=str(entry.get("impact_on") or "none").strip().lower() if quantified else "none",
                    quantified=quantified,
                )
            )
            continue
        claim = _clip(entry, 240)
        if claim:
            items.append(EvidenceItem(claim=claim))
    return items


def _fallback(result: DeepResult, candidate: Candidate, evidence_text: str, extra_flags: list[str]) -> QualResult:
    """No-LLM mapping straight off the dive's stance and debate text.

    Evidence items come from the bull/bear points the dive itself produced,
    quantified only when the point's own text carries a percentage figure.
    """
    thesis = result.thesis
    stance = (thesis.stance if thesis else "") or ""
    # Score the debate deterministically (no adapter call), then reconcile with
    # the stance exactly as the LLM path does: decisive debate wins, the stance
    # label stands inside the balanced band.
    rows = driver_rows(thesis)
    agg = aggregate_scores(rows)
    supports, score_flags = _resolved_supports(agg["s"], stance, candidate.side)
    supports = stance_supports(stance, candidate.side) if supports is None and agg["s"] is None else supports
    flags = ["deepdive_stance_fallback"] + extra_flags + score_flags
    if (thesis.confidence if thesis else "") == "low":
        flags.append("low_confidence")
    for_items: list[EvidenceItem] = []
    against_items: list[EvidenceItem] = []
    if thesis:
        bull_items = [
            EvidenceItem(claim=_clip(f"{b.point} — {b.evidence}".strip(" —"), 240))
            for b in thesis.bull_case[:4]
        ]
        bear_items = [
            EvidenceItem(claim=_clip(f"{b.point} — {b.evidence}".strip(" —"), 240))
            for b in thesis.bear_case[:4]
        ]
        figures = _figures_in(evidence_text)
        for item in bull_items + bear_items:
            found = _figures_in(item.claim)
            if found and any(abs(abs(f) - abs(g)) < 0.15 for f in found for g in figures):
                item.impact_pct = found[0]
                item.impact_on = "none"
                item.quantified = True
        if candidate.side == Side.LONG:
            for_items, against_items = bull_items, bear_items
        else:
            for_items, against_items = bear_items, bull_items
    why = _clip(thesis.thesis if thesis else result.error, 480)
    if supports is False and not why:
        why = f"the dive reads {stance or 'unclear'}, which does not support this side's trade."
    if why and stance:
        s_text = f" | S={agg['s']:+.2f}" if agg["s"] is not None else ""
        why = f"[dive: {stance}{s_text}] {why}"
    qual = QualResult(
        supports_outlier=supports,
        red_flags=flags,
        kpis=[d.name for d in thesis.drivers[:5]] if thesis else [],
        operating_plan="",
        summary=why,
        why=why,
        evidence_quotes=[],
        evidence_for=for_items,
        evidence_against=against_items,
        filing_direction=_STANCE_DIRECTION.get(stance.lower(), "silent"),
        direction_basis=_clip(thesis.confidence_why if thesis else "", 240),
        momentum_durability="unclear",
        durability_basis="durability needs the verdict model; fallback maps stance only",
        themes=theme_labels(evidence_text),
        denial_reason="" if supports is not False else f"dive stance {stance or 'unclear'} argues against this side",
    )
    _apply_scores(qual, rows)
    return qual


def qual_from_deepdive(
    result: DeepResult,
    candidate: Candidate,
    evidence_text: str,
) -> QualResult:
    """The deep dive as the qualitative verdict for one candidate.

    `evidence_text` is the rendered dive (or an equivalent packing of its
    findings); quantified magnitudes are verified against it, so pass the same
    text that was shown to the verifier model.
    """
    flags: list[str] = []
    if result.error:
        flags.append(f"deepdive_incomplete: {result.error[:120]}")
    if not result.llm_used:
        flags.append("deepdive_llm_unavailable")
    if result.thesis is None or not llm_available():
        return _fallback(result, candidate, evidence_text, flags)
    answered_by: list[str] = []
    wanted_model = verdict_model()
    try:
        payload = _adapter_call(result, candidate, evidence_text, answered_by)
    except Exception as exc:
        log(f"deepdive verdict {candidate.ticker}: adapter FAIL {exc}; using stance fallback")
        return _fallback(result, candidate, evidence_text, flags + ["verdict_adapter_failed"])
    raw = payload.get("supports_outlier")
    supports = None if raw in (None, "null") else bool(raw)
    # Quantitative layer first: the debate is scored deterministically, then
    # the score and the synthesised stance are reconciled (score wins when the
    # debate is decisive; the stance label stands inside the balanced band).
    rows = driver_rows(result.thesis)
    agg = aggregate_scores(rows)
    resolved, score_flags = _resolved_supports(agg["s"], result.thesis.stance, candidate.side)
    flags.extend(score_flags)
    if supports is not None and resolved is not None and supports != resolved:
        flags.append("verdict_adapter_bool_overridden_by_score")
    if supports is None and resolved is None:
        # A vacuous adapter answer defers to the dive's own stance rather than
        # silently zeroing the idea.
        supports = stance_supports(result.thesis.stance, candidate.side)
        flags.append("verdict_adapter_fell_back_to_stance")
    else:
        supports = resolved
    if answered_by and answered_by[0] != wanted_model:
        flags.append(f"verdict_model_downgraded_to_{answered_by[0]}")
    for_items = _evidence_items(payload.get("evidence_for"))
    against_items = _evidence_items(payload.get("evidence_against"))
    verified_for, stripped_for = _verify_quantified(for_items, evidence_text)
    verified_against, stripped_against = _verify_quantified(against_items, evidence_text)
    if stripped_for or stripped_against:
        flags.append(f"unverifiable_magnitude_stripped x{stripped_for + stripped_against}")
    why = _clip(payload.get("why"), 480)
    stance = result.thesis.stance
    if why and stance:
        s_text = f" | S={agg['s']:+.2f}" if agg["s"] is not None else ""
        why = f"[dive: {stance}{s_text}] {why}"
    if supports is False and not _clip(payload.get("denial_reason")) and agg["s"] is not None:
        payload["denial_reason"] = (
            f"evidence score {agg['s']:+.2f} of -2..+2 (long {agg['long']}/10, short {agg['short']}/10) "
            f"does not support this side's trade"
        )
    denial = _clip(payload.get("denial_reason")) if supports is False else ""
    filing_direction = str(payload.get("filing_direction") or "").strip().lower()
    if filing_direction not in {"improving", "deteriorating", "mixed", "silent"}:
        filing_direction = _STANCE_DIRECTION.get(stance, "silent")
    durability = str(payload.get("momentum_durability") or "").strip().lower()
    if durability not in {"building", "intact", "fading", "exhausted", "unclear"}:
        durability = "unclear"
    kpis = [str(k).strip()[:80] for k in (payload.get("kpis") or []) if str(k).strip()][:6]
    qual = QualResult(
        supports_outlier=supports,
        red_flags=flags,
        kpis=kpis,
        operating_plan=_clip(payload.get("operating_plan")),
        summary=why or _clip(result.thesis.thesis, 240),
        why=why,
        evidence_quotes=[],
        evidence_for=verified_for,
        evidence_against=verified_against,
        filing_direction=filing_direction,
        direction_basis=_clip(payload.get("direction_basis")),
        momentum_durability=durability,
        durability_basis=_clip(payload.get("durability_basis")),
        themes=theme_labels(evidence_text),
        denial_reason=denial,
    )
    _apply_scores(qual, rows)
    return qual


def deepdive_extra(result: DeepResult, report_ideas_rel: str) -> dict:
    """The compact deep-dive summary stored on idea.extra for the viewer."""
    thesis = result.thesis
    return {
        "stance": thesis.stance if thesis else "",
        "confidence": thesis.confidence if thesis else "",
        "as_of": result.as_of,
        "findings": len(result.research.findings) if result.research else 0,
        "debate_rounds": len(thesis.debate) if thesis else 0,
        "report": report_ideas_rel,
        "error": result.error or "",
    }
