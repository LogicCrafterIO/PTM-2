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

from ptm.deepsearch.models import DeepResult, Thesis
from ptm.llm import JSON_HINT, _clip, chat_json, llm_available, verdict_model
from ptm.log import log
from ptm.models import Candidate, EvidenceItem, QualResult, Side
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
    supports = stance_supports(stance, candidate.side)
    flags = ["deepdive_stance_fallback"] + extra_flags
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
    return QualResult(
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
    if supports is None:
        # A vacuous adapter answer defers to the dive's own stance rather than
        # silently zeroing the idea.
        supports = stance_supports(result.thesis.stance, candidate.side)
        flags.append("verdict_adapter_fell_back_to_stance")
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
        why = f"[dive: {stance}] {why}"
    denial = _clip(payload.get("denial_reason")) if supports is False else ""
    filing_direction = str(payload.get("filing_direction") or "").strip().lower()
    if filing_direction not in {"improving", "deteriorating", "mixed", "silent"}:
        filing_direction = _STANCE_DIRECTION.get(stance, "silent")
    durability = str(payload.get("momentum_durability") or "").strip().lower()
    if durability not in {"building", "intact", "fading", "exhausted", "unclear"}:
        durability = "unclear"
    kpis = [str(k).strip()[:80] for k in (payload.get("kpis") or []) if str(k).strip()][:6]
    return QualResult(
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
