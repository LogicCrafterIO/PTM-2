"""Bull/bear debate and synthesis for the deep dive.

Four LLM passes over the gathered evidence:
  1. identify the 3-5 drivers the whole thesis hinges on
  2. build the strongest honest bull case from the findings
  3. build the strongest honest bear case from the SAME findings
  4. debate per-driver with a moderator verdict, then synthesise
"""

from __future__ import annotations

import json

from ptm.deepsearch.models import (
    BearPoint,
    BullPoint,
    DebateRound,
    Driver,
    SourceRef,
    Thesis,
)
from ptm.llm import JSON_HINT, chat_json, verdict_model

CASE_SYSTEM = (
    "You are a skeptical equity research analyst. You will receive findings gathered from web research "
    "about ONE company plus the company's own SEC-filing context. Build the STRONGEST HONEST case for "
    "the requested side. Rules: argue only from the evidence given, never invent a number; cite which "
    "finding index supports each point; a weak case stated honestly beats a strong case invented. "
    + JSON_HINT
)

DRIVER_LIST_SYSTEM = (
    "You are an equity research analyst identifying the 3-5 key qualitative drivers that will decide "
    "whether a company's fundamental trajectory improves or deteriorates over the next 12-24 months. "
    "Drivers are things like: pricing power, customer concentration, competitive displacement, regulatory "
    "risk, capacity constraints, management execution, end-market demand. A good driver is specific to "
    "this company, arguable (a reasonable bull and bear can disagree), and checkable against evidence. "
    + JSON_HINT
)

DRIVER_DEBATE_SYSTEM = (
    "You are moderating a structured bull-vs-bear debate on ONE company's key drivers. "
    "For each driver the bull and the bear argue from the evidence, then you call the round: "
    "who carried it and what evidence would flip the call. The bear must be a real bear, not a "
    "strawman; the bull must answer the bear's strongest point, not ignore it. " + JSON_HINT
)

SYNTH_SYSTEM = (
    "You are the lead analyst writing the final view after a bull-vs-bear debate on ONE company. "
    "You have the debate rounds with verdicts, both sides' points, and the underlying findings. "
    "Write the thesis the evidence actually supports — not a compromise, not a restatement. If the "
    "evidence is genuinely mixed, say balanced and say what decides it. Every driver claim cites a "
    "finding index. Falsifiers must be observable: a metric, an event, a number that would change the call. "
    + JSON_HINT
)


def _clip(text: object, limit: int = 400) -> str:
    return str(text or "").strip()[:limit]


def _call_json(system: str, user: str, used_out: list[str] | None = None) -> dict:
    """chat_json with one retry on a vacuous reply.

    A reasoning model that runs out of tokens mid-thought returns `{}` or an
    object without the expected key - which parses as valid JSON, so the
    existing truncation retry never fires. Trim the context (the tail blocks
    carry the JSON keys' data) and ask once more on the same model.
    """
    payload = chat_json(system, user, model=verdict_model(), used_out=used_out)
    if payload:
        return payload
    trimmed = user[: len(user) // 2]
    return chat_json(
        system + " Reply with the smaller JSON object. Keep every string under 240 characters.",
        trimmed,
        model=verdict_model(),
    )


def _source_of(ref: dict, findings: list[dict]) -> SourceRef:
    """Resolve a finding index back to its source."""
    idx = ref.get("finding_idx") or ref.get("source_idx")
    try:
        i = int(idx)
        if 1 <= i <= len(findings):
            f = findings[i - 1]
            src = f.get("source") or {}
            if isinstance(src, dict):
                return SourceRef(title=str(src.get("title") or ""), url=str(src.get("url") or ""))
    except (TypeError, ValueError):
        pass
    return SourceRef()


def findings_block(findings: list[dict]) -> str:
    return "\n".join(f"[{i}] {f.get('claim') or ''}" for i, f in enumerate(findings, 1))


def identify_drivers(findings: list[dict], filing_context: str, who: str, macro_block: str = "") -> list[dict]:
    """The 3-5 drivers the debate will be structured around."""
    if not findings:
        return []
    macro_part = f"\nMacro / ISM backdrop (weigh this alongside company evidence):\n{macro_block}\n" if macro_block else ""
    payload = _call_json(
        DRIVER_LIST_SYSTEM,
        f"Company: {who}\n\nFindings (numbered):\n{findings_block(findings)[:16000]}\n\n"
        f"SEC-filing context:\n{filing_context[:3000]}\n\n"
        f"{macro_part}"
        'Write JSON: {"drivers": [{"name": "...", "bull_read": "...", "bear_read": "..."}]}',
    )
    out = []
    for d in (payload.get("drivers") or [])[:5]:
        name = _clip(d.get("name"), 80)
        if not name:
            continue
        out.append({"name": name, "bull_read": _clip(d.get("bull_read"), 300), "bear_read": _clip(d.get("bear_read"), 300)})
    return out


def build_case(findings: list[dict], filing_context: str, who: str, side: str, macro_block: str = "") -> list[dict]:
    """Bull or bear points as plain dicts: point, evidence, source, weight."""
    label = "BULL" if side == "bull" else "BEAR"
    key = "strength" if side == "bull" else "severity"
    scale = "strong|medium|weak" if side == "bull" else "severe|material|minor"
    macro_part = (
        f"Macro / ISM backdrop (may be cited where it genuinely bears on a point):\n{macro_block}\n\n"
        if macro_block
        else ""
    )
    payload = _call_json(
        CASE_SYSTEM,
        f"Company: {who}\n\nBuild the strongest honest {label} case.\n\n"
        f"Findings (numbered):\n{findings_block(findings)[:20000]}\n\n"
        f"SEC-filing context (background only; cite web findings for claims):\n{filing_context[:4000]}\n\n"
        f"{macro_part}"
        f'Write JSON: {{"points": [{{"point": "...", "evidence": "...", "finding_idx": 1, "{key}": "{scale}"}}]}}',
    )
    out = []
    for p in (payload.get("points") or [])[:6]:
        point = _clip(p.get("point"))
        if not point:
            continue
        out.append(
            {
                "point": point,
                "evidence": _clip(p.get("evidence"), 300),
                "source": _source_of(p, findings),
                key: _clip(p.get(key), 12).lower() or ("medium" if side == "bull" else "material"),
            }
        )
    return out


def run_debate(
    drivers: list[dict],
    findings: list[dict],
    filing_context: str,
    who: str,
    used_out: list[str] | None = None,
    macro_block: str = "",
) -> tuple[list[DebateRound], list[str], str, str]:
    """Structured bull-vs-bear per driver; the moderator calls each round.

    Returns (rounds, falsifiers, confidence, confidence_why).
    """
    if not drivers:
        return [], [], "medium", "no drivers identified"
    macro_part = (
        f"Macro / ISM backdrop (the bull and bear may each use it where it helps them):\n{macro_block}\n\n"
        if macro_block
        else ""
    )
    payload = _call_json(
        DRIVER_DEBATE_SYSTEM,
        f"Company: {who}\n\nDrivers to debate:\n{json.dumps(drivers, indent=2)}\n\n"
        f"Findings (numbered):\n{findings_block(findings)[:20000]}\n\n"
        f"SEC-filing context (background):\n{filing_context[:3000]}\n\n"
        f"{macro_part}"
        'Write JSON: {"rounds": [{"driver": "...", "bull": "...", "bull_finding_idx": 1, '
        '"bear": "...", "bear_finding_idx": 2, "verdict": "who won and why", '
        '"verdict_side": "bull|bear|tie", "falsifier": "what would flip this call"}], '
        '"confidence": "high|medium|low", "confidence_why": "one sentence"}',
        used_out=used_out,
    )
    rounds: list[DebateRound] = []
    falsifiers: list[str] = []
    for r in (payload.get("rounds") or [])[:5]:
        driver_name = _clip(r.get("driver"), 80)
        if not driver_name:
            continue
        rounds.append(
            DebateRound(
                driver=driver_name,
                bull=_clip(r.get("bull")),
                bull_source=_source_of({"finding_idx": r.get("bull_finding_idx")}, findings),
                bear=_clip(r.get("bear")),
                bear_source=_source_of({"finding_idx": r.get("bear_finding_idx")}, findings),
                verdict=_clip(r.get("verdict")),
                verdict_side=_clip(r.get("verdict_side"), 8).lower(),
            )
        )
        fals = _clip(r.get("falsifier"), 240)
        if fals:
            falsifiers.append(fals)
    return rounds, falsifiers, _clip(payload.get("confidence"), 8).lower() or "medium", _clip(payload.get("confidence_why"), 400)


def synthesize(
    rounds: list[DebateRound],
    bull: list[dict],
    bear: list[dict],
    findings: list[dict],
    filing_context: str,
    who: str,
    used_out: list[str] | None = None,
    macro_block: str = "",
) -> Thesis:
    """The final thesis, written after the debate, not before.

    A reasoning model can burn its whole token budget thinking and return an
    empty object, which parses as valid JSON and would otherwise read as
    "no view". One retry with trimmed context, then fail loudly so the run
    reports an incomplete dive instead of an empty verdict.
    """
    macro_part = (
        f"Macro / ISM backdrop (state how it shifts the balance if at all):\n{macro_block}\n\n"
        if macro_block
        else ""
    )
    user = (
        f"Company: {who}\n\nDebate outcome:\n{json.dumps([r.model_dump() for r in rounds], indent=2, default=str)[:8000]}\n\n"
        f"Bull points: {json.dumps(bull, default=str)[:3000]}\n"
        f"Bear points: {json.dumps(bear, default=str)[:3000]}\n\n"
        f"SEC-filing context:\n{filing_context[:2500]}\n\n"
        f"{macro_part}"
        'Write JSON: {"stance": "constructive|cautious|balanced|unclear", "thesis": "...", '
        '"drivers": [{"name": "...", "direction": "tailwind|headwind|neutral", "evidence": "...", '
        '"source_idx": 1, "confidence": "high|medium|low", '
        '"score": <number -2..+2>, "category": "valuation|fundamentals|catalysts|competitive|risk", '
        '"score_why": "one sentence of reasoning"}], '
        '"falsifiers": ["..."], "confidence": "high|medium|low", "confidence_why": "..."}\n'
        "SCORE EVERY driver you list, in the same pass that you choose the stance: the score is YOUR "
        "judgement of that driver's debate from the standpoint of the STOCK — positive when the bull "
        "side won (evidence constructive for the shares), negative when the bear won — with magnitude "
        "±0.5 marginal, ±1.0 clear, ±1.5 strong, ±2.0 decisive, consistent with the round's verdict_side. "
        "The category is the pillar the driver belongs to: valuation (the multiple, premium or discount, "
        "re-rating), fundamentals (revenue, margins, backlog, guidance, efficiency), catalysts (dated "
        "events that could re-rate the name), competitive (market share, moat, rivals), risk (anything "
        "that could break the thesis). The why must reason the score, not restate the debate. These "
        "scores aggregate, with fixed category weights, into the verdict's evidence score; your stance "
        "should follow from the same weighing."
    )
    payload = _call_json(SYNTH_SYSTEM, user, used_out=used_out)
    if not str(payload.get("thesis") or "").strip():
        payload = chat_json(
            SYNTH_SYSTEM + " Keep the thesis under 900 characters.",
            user[:14000],
            model=verdict_model(),
        )
    if not str(payload.get("thesis") or "").strip():
        raise RuntimeError("synthesis returned no thesis text")
    drivers = []
    for d in (payload.get("drivers") or [])[:5]:
        name = _clip(d.get("name"), 80)
        if not name:
            continue
        try:
            score = None if d.get("score") in (None, "", "null") else max(-2.0, min(2.0, float(d.get("score"))))
        except (TypeError, ValueError):
            score = None
        drivers.append(
            Driver(
                name=name,
                direction=_clip(d.get("direction"), 12).lower() or "neutral",
                evidence=_clip(d.get("evidence"), 300),
                source=_source_of(d, findings),
                confidence=_clip(d.get("confidence"), 8).lower() or "medium",
                score=score,
                category=_clip(d.get("category"), 20).lower(),
                score_why=_clip(d.get("score_why"), 300),
            )
        )
    return Thesis(
        stance=_clip(payload.get("stance"), 16).lower() or "unclear",
        thesis=_clip(payload.get("thesis"), 1600),
        drivers=drivers,
        bull_case=[
            BullPoint(point=b["point"], evidence=b["evidence"], source=b["source"], strength=b.get("strength", "medium"))
            for b in bull
        ],
        bear_case=[
            BearPoint(point=b["point"], evidence=b["evidence"], source=b["source"], severity=b.get("severity", "material"))
            for b in bear
        ],
        debate=rounds,
        falsifiers=[_clip(f, 240) for f in (payload.get("falsifiers") or [])[:6] if _clip(f)],
        confidence=_clip(payload.get("confidence"), 8).lower() or "medium",
        confidence_why=_clip(payload.get("confidence_why"), 400),
    )