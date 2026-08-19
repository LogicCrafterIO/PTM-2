from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timezone
from threading import Lock

from openai import OpenAI

from ptm.config import data_dir, env, toml_settings
from ptm.io import write_json
from ptm.log import log
from ptm.models import Candidate, CatalystResult, EvidenceItem, MacroSnapshot, QualResult, Side
from ptm.timing_prm import catalyst_window, earnings_in_window, normalize_earnings_date

JSON_HINT = "Reply with a single JSON object only. No markdown."
GENERIC_KPIS = {"revenue", "net_income", "ebit", "cash", "debt", "assets", "equity", "interest"}
HEADLINE_RE = re.compile(r"\?$|outpaced|do options traders|what to expect", re.I)


def llm_available() -> bool:
    settings = env()
    return bool(settings.nvidia_api_key or settings.openai_api_key)


def client() -> OpenAI:
    settings = env()
    if settings.nvidia_api_key:
        return OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key, timeout=45.0)
    if settings.openai_api_key:
        return OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key, timeout=90.0)
    raise RuntimeError("No LLM API key set")


def model_name() -> str:
    settings = env()
    if settings.nvidia_api_key:
        return settings.nvidia_model
    return settings.openai_model


TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _repair_json(text: str) -> str | None:
    """Fix the syntax error small models actually make.

    A trailing comma before a closing brace or bracket accounted for every JSON
    failure observed across a 308-name run (~2% of calls). Losing an idea's
    catalysts to a stray character is not a fair trade.
    """
    repaired = TRAILING_COMMA_RE.sub(r"\1", text)
    return repaired if repaired != text else None


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*)\n```$", text, flags=re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    cleaned = "".join(ch if (ch >= " " or ch in "\n\t\r") else " " for ch in text)
    for attempt in (cleaned, _repair_json(cleaned)):
        if attempt is None:
            continue
        try:
            payload = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    match = re.search(r"\{", cleaned)
    if not match:
        raise json.JSONDecodeError("No JSON object", cleaned, 0)
    tail = cleaned[match.start() :]
    try:
        payload, _ = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError:
        payload, _ = json.JSONDecoder().raw_decode(_repair_json(tail) or tail)
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("JSON root is not an object", cleaned, 0)
    return payload




# --- LLM pacing --------------------------------------------------------------
# Running ideas concurrently discovered the provider's limit the expensive way:
# 217 throttle retries in one run, and 5 ideas that exhausted their retries and
# lost their catalyst analysis outright. Retrying is a backstop, not a plan.
# Pace requests deliberately instead, the same way SEC calls are paced, so 429s
# become rare rather than routine.

_LLM_RATE_LOCK = Lock()
_LLM_LAST_CALL = [0.0]


def _llm_max_rps() -> float:
    return float((toml_settings().get("llm") or {}).get("max_rps") or 0.0)


def _pace_llm() -> None:
    """Block until this process may issue another completion request."""
    rate = _llm_max_rps()
    if rate <= 0:
        return
    min_gap = 1.0 / rate
    with _LLM_RATE_LOCK:
        now = time.monotonic()
        wait = _LLM_LAST_CALL[0] + min_gap - now
        if wait > 0:
            time.sleep(wait)
            now = now + wait
        _LLM_LAST_CALL[0] = now


# Concurrency makes provider throttling a normal event, not an exception.
RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF = 2.5
_THROTTLE_MARKERS = ("429", "too many requests", "rate limit", "ratelimit", "overloaded", "503", "502")


def _is_throttled(exc: Exception) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status in {429, 502, 503}:
        return True
    return any(marker in text for marker in _THROTTLE_MARKERS)


FALLBACK_MODELS = [
    "meta/llama-3.1-8b-instruct",
]


def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    used_out: list[str] | None = None,
    _retried: bool = False,
) -> dict:
    """Chat completion returning parsed JSON.

    `used_out`, if given, receives the model that actually answered.
    FALLBACK_MODELS means a pinned model can quietly be replaced by a smaller
    one - on a first run of the 70B, 9 of 12 verdicts silently came back from
    the 8B. A caller that pins a model for a reason needs to know when that did
    not happen.
    """
    cfg = toml_settings()["llm"]
    log_dir = data_dir("llm_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    last_error = None
    primary = model or model_name()
    models = [primary] + [m for m in FALLBACK_MODELS if m != primary]
    content = "{}"
    used = primary
    for used in models:
        for attempt in range(RATE_LIMIT_RETRIES):
            try:
                _pace_llm()
                response = client().chat.completions.create(
                    model=used,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=cfg["temperature"],
                    max_tokens=cfg["max_tokens"],
                )
                content = response.choices[0].message.content or "{}"
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                # Running ideas concurrently makes 429s routine rather than
                # exceptional. Without this an idea silently lost its catalysts
                # to a transient throttle, which reads identically to "no
                # catalysts found". Back off and retry before giving up.
                if _is_throttled(exc) and attempt < RATE_LIMIT_RETRIES - 1:
                    delay = RATE_LIMIT_BACKOFF * (2**attempt) + random.uniform(0, 0.4)
                    log(f"llm: throttled, retrying in {delay:.1f}s ({attempt + 1}/{RATE_LIMIT_RETRIES - 1})")
                    time.sleep(delay)
                    continue
                break
        if last_error is None:
            break
    if last_error and content == "{}":
        raise last_error
    write_json(
        log_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json",
        {"model": used, "system": system, "user": user[:4000], "content": content},
    )
    if used_out is not None:
        used_out.append(used)
    try:
        return _extract_json(content)
    except json.JSONDecodeError:
        if _retried:
            raise
        return chat_json(
            system + " Return a smaller JSON object. Keep every string under 240 characters. Close all quotes.",
            user[: min(len(user), 4000)],
            model=model,
            used_out=used_out,
            _retried=True,
        )




# Beyond this a stated percentage change is almost certainly an absolute number
# the model mislabelled. Real accretion does not run to four figures.
MAX_PLAUSIBLE_IMPACT_PCT = 500.0


def _evidence_items(raw: object) -> list[EvidenceItem]:
    """Parse evidence into items, tolerating a model that returns bare strings.

    A magnitude is kept only when the model both flagged it as quantified and
    supplied a number; anything else is recorded as an unquantified claim rather
    than being allowed to carry invented precision into the conviction score.
    """
    items: list[EvidenceItem] = []
    for entry in (raw or [])[:5]:
        if isinstance(entry, dict):
            claim = _clip(entry.get("claim") or entry.get("evidence") or entry.get("reason"), 240)
            if not claim:
                continue
            impact = entry.get("impact_pct")
            try:
                impact = None if impact in (None, "", "null") else float(impact)
            except (TypeError, ValueError):
                impact = None
            # A percentage change of this size is almost always an absolute
            # figure misread as a percent - a $3.7bn capital plan came back as
            # "+3700%". The magnitude is dropped; the claim itself is kept.
            if impact is not None and abs(impact) > MAX_PLAUSIBLE_IMPACT_PCT:
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


def verdict_model() -> str:
    """Model for the qualitative verdict, which may differ from the default.

    This is the single call the book depends on: everything upstream of it is
    deterministic, and it alone decides which names survive. It is also the step
    where a small model demonstrably failed - returning a boolean that
    contradicted its own stated evidence. One call per name makes a larger model
    cheap insurance. Extraction and templating stay on the default.
    """
    configured = str((toml_settings().get("llm") or {}).get("verdict_model") or "").strip()
    return configured or model_name()


def macro_narrative(snapshot: MacroSnapshot) -> str:
    if not llm_available():
        return "LLM skipped: no API key. Bias from deterministic score only."
    data = snapshot.model_dump()
    payload = chat_json(
        "You are a professional long/short equity macro analyst following a leading-indicator dashboard. "
        "Interpret direction only, not magnitude. " + JSON_HINT,
        "Write JSON with keys narrative (string) and sector_tilts (array of {sector, tilt: long|short|neutral, why}). "
        "Do not replace the deterministic ISM sector_tilts already on the dashboard; comment on them. "
        f"Dashboard:\n{json.dumps(data, default=str)[:6000]}",
    )
    return str(payload.get("narrative") or "")


def sanitize_kpis(kpis: list | None) -> tuple[list[str], bool]:
    cleaned: list[str] = []
    stripped = False
    for raw in kpis or []:
        token = str(raw).strip()
        key = token.lower().replace(" ", "_")
        if key in GENERIC_KPIS or token.lower() in GENERIC_KPIS:
            stripped = True
            continue
        if token:
            cleaned.append(token)
    return cleaned, stripped


def filter_non_earnings(raw_items: list | None, low_days: int | None = None, high_days: int | None = None) -> list[str]:
    if low_days is None or high_days is None:
        window_low, window_high = catalyst_window()
        low_days = window_low if low_days is None else low_days
        high_days = window_high if high_days is None else high_days
    kept: list[str] = []
    for item in raw_items or []:
        event = ""
        date_raw: object | None = None
        if isinstance(item, dict):
            event = str(item.get("event") or item.get("title") or "").strip()
            date_raw = item.get("date") or item.get("event_date")
            why = str(item.get("why") or "").strip()
            if why and why.lower() not in event.lower():
                event = f"{event} — {why}" if event else why
        else:
            event = str(item).strip()
            date_raw = event
        if not event:
            continue
        if HEADLINE_RE.search(event) or "|" in event or event.count("%") >= 2:
            continue
        iso = normalize_earnings_date(date_raw)
        if not iso:
            iso = normalize_earnings_date(event)
        if not iso:
            continue
        in_window, parsed = earnings_in_window(iso, low_days=low_days, high_days=high_days)
        if not in_window or not parsed:
            continue
        kept.append(f"{event} ({parsed})" if parsed not in event else event)
    return kept


def _clip(value: object, n: int = 240) -> str:
    return str(value or "").strip()[:n]



# How demanding the qualitative gate is. Measured pass rates on this universe:
#   consistent -> ~80%   strict -> ~55%
# (The wording this replaced scored 0%, which is a gate that carries no
# information at all.) Which of the two is right is a process judgement about
# how much work the qualitative step should do beyond the quant screen, so it
# is a setting rather than a hardcoded choice. See docs/FEATURE-LIMITATIONS.md.
VERDICT_BARS = {
    "consistent": (
        "Work in this order: list evidence_for (supporting the trade) and evidence_against, then set "
        "supports_outlier so it AGREES with them. If evidence_for is non-empty and not outweighed by "
        "evidence_against, supports_outlier MUST be true. Never contradict your own evidence. "
    ),
    "strict": (
        "Work in this order: list evidence_for and evidence_against, then set supports_outlier so it "
        "AGREES with them. The bar is SPECIFICITY: evidence_for counts only when it is concrete and "
        "quantified - named products, segment growth rates, backlog figures, margin or volume numbers. "
        "Mission statements, strategy language, 'focused on growth', or the mere existence of a plan "
        "are NOT evidence. If the strongest thing you can say is that the company has a plan or "
        "operates in a good market, answer false. Answer true only when specific evidence materially "
        "outweighs the evidence against. Never contradict your own evidence. "
    ),
}


def _verdict_bar() -> str:
    choice = str((toml_settings().get("llm") or {}).get("qualitative_bar") or "consistent").lower()
    return VERDICT_BARS.get(choice, VERDICT_BARS["consistent"])


def qualitative(
    candidate: Candidate,
    filing_excerpt: str,
    thin: bool = False,
    skip_llm: bool = False,
) -> QualResult:
    if skip_llm or not llm_available():
        return QualResult(
            supports_outlier=None,
            summary="LLM skipped; qualitative gate deferred.",
            kpis=[],
            red_flags=["llm_skipped"],
        )
    if thin or not (filing_excerpt or "").strip():
        return QualResult(
            supports_outlier=None,
            summary="Insufficient research pack to decide if the operating plan supports the outlier.",
            kpis=[],
            red_flags=["insufficient_evidence"],
        )
    pack = filing_excerpt[: toml_settings()["llm"]["max_filing_chars"]]
    extract_system = (
        "Extract operating facts from the research pack. Do not decide if this is a trade. "
        "A Yahoo summary, headlines, 8-K, MD&A, and ISM comments ARE valid sources. "
        "KPIs must be operating drivers (segments, products, backlog, utilization, volumes, pricing), "
        "not statement lines (revenue, net_income, ebit, cash, debt). "
        "Keep every string under 240 characters. " + JSON_HINT
    )
    extract_user = (
        "Return JSON keys: business_in_one_line (string), operating_plan (string), "
        "kpis (string[3-6]), red_flags (string[]), ism_link (string), quotes (string[]).\n"
        f"Ticker={candidate.ticker} side={candidate.side.value} industry={candidate.industry} "
        f"ISM={candidate.ism_why}\n\nResearch pack:\n{pack}"
    )
    pass_a_failed = False
    extract: dict = {}
    try:
        extract = chat_json(extract_system, extract_user)
    except (json.JSONDecodeError, Exception):
        pass_a_failed = True
        extract = {}

    kpis, stripped = sanitize_kpis(list(extract.get("kpis") or [])[:6])
    flags = [str(x) for x in (extract.get("red_flags") or [])]
    quotes = [_clip(q, 200) for q in (extract.get("quotes") or []) if str(q).strip()][:4]
    if stripped:
        flags.append("generic_kpis_stripped")
    extract_summary = {
        "business": _clip(extract.get("business_in_one_line")),
        "operating_plan": _clip(extract.get("operating_plan")),
        "kpis": kpis,
        "ism_link": _clip(extract.get("ism_link")),
        "red_flags": flags,
        "quotes": quotes,
    }
    # The earlier wording ("does the plan support the outlier") was ambiguous for
    # shorts: models read deterioration as a reason to REJECT a discount short,
    # the opposite of what it means. Measured over 100 real names it produced a
    # 0% pass rate — a gate that never opens carries no information. The verdict
    # is now asked as a side-specific question, and the model must enumerate its
    # evidence before committing to a boolean that agrees with it.
    verdict_system = (
        "You are doing PTM qualitative processing on ONE name. A good company is not automatically a "
        "good trade, and a bad company is not automatically a good short.\n"
        "You are given a quantitative outlier: a P/E far from its sector. Say whether the operating "
        "evidence EXPLAINS that gap.\n"
        "For a LONG (premium multiple): answer true when the evidence shows growth, acceleration, "
        "backlog, pricing power or a credible plan that could grow into the multiple.\n"
        "For a SHORT (discount multiple): answer true when the evidence shows the discount is DESERVED "
        "- declining volumes, shrinking margins, lost share, one-off EPS, structural decline or no "
        "credible plan. Deterioration is the CONFIRMING evidence for a short, not a reason to reject it.\n"
        + "Every evidence item is an object: {claim, metric, impact_pct, impact_on, quantified}. "
        "The pack contains reported figures, usually in the earnings release: revenue, margins, "
        "segment growth, guidance. For EVERY claim you make, search the pack for the number that "
        "sizes it and put it in impact_pct. Prefer evidence the pack quantifies - a claim you can "
        "size is stronger than one you cannot, so reach for the sized ones first. "
        "impact_pct is a CHANGE - growth, decline or accretion, as in \"revenue grew 9%\" or "
        "\"backlog up 69%\". A standing level or ratio such as \"R&D is 95% of revenue\" is a "
        "useful claim but not a change, so leave impact_pct null for it. "
        "Set quantified=true only when that change is IN the pack, either stated outright or "
        "computable from two figures it gives. Never estimate, infer or guess a magnitude; if the "
        "pack does not size the claim, set quantified=false, impact_pct=null and "
        "impact_on=\"none\". A precise number you invented is worse than no number at all. "
        "impact_on must be earnings, revenue, margin or none, describing what the change moves. "
        + _verdict_bar()
        + "supports_outlier must be true or false, never null. "
        "Keep every string under 240 characters. " + JSON_HINT
    )
    ratio = ""
    if candidate.pe1 and candidate.sector_pe1:
        ratio = f" ({candidate.pe1 / candidate.sector_pe1:.1f}x sector)"
    ask = (
        "does the evidence justify PAYING this premium?"
        if candidate.side == Side.LONG
        else "does the evidence show this discount is DESERVED?"
    )
    verdict_user = (
        "Return JSON keys: evidence_for (array of {claim, metric, impact_pct, impact_on, "
        "quantified}), evidence_against (same shape), "
        "supports_outlier (bool), why (string, 2-4 sentences), denial_reason (string).\n"
        f"Side={candidate.side.value}. P/E {candidate.pe1} vs sector {candidate.sector_pe1}{ratio}. "
        f"EG case={candidate.eg_case}.\n"
        f"Question: {ask}\n\n"
        f"Extract:\n{json.dumps(extract_summary, default=str)}"
    )
    verdict: dict = {}
    wanted_model = verdict_model()
    answered_by: list[str] = []
    try:
        verdict = chat_json(verdict_system, verdict_user, model=wanted_model, used_out=answered_by)
        if answered_by and answered_by[0] != wanted_model:
            # The gate ran on something smaller than intended. Say so on the idea.
            flags.append(f"verdict_model_downgraded_to_{answered_by[0]}")
    except (json.JSONDecodeError, Exception):
        if pass_a_failed:
            return QualResult(
                supports_outlier=None,
                summary="LLM JSON failed on extract and verdict.",
                kpis=kpis,
                red_flags=flags + ["llm_json_failed"],
                operating_plan=_clip(extract.get("operating_plan")),
                why="",
                evidence_quotes=quotes,
                denial_reason="llm_json_failed",
            )
        verdict = {
            "supports_outlier": False,
            "why": "Verdict JSON failed after a usable extract; not treating as a pass.",
            "denial_reason": "verdict JSON unreadable",
        }
        flags.append("llm_json_failed_verdict")

    raw = verdict.get("supports_outlier")
    if raw is None or raw == "null":
        if pass_a_failed:
            supports = None
            flags.append("llm_json_failed")
        else:
            supports = False
            flags.append("llm_json_failed_verdict")
    else:
        supports = bool(raw)
    for_items = _evidence_items(verdict.get("evidence_for"))
    against_items = _evidence_items(verdict.get("evidence_against"))
    # Surface, but do not silently overturn, a verdict that argues against itself.
    if supports is False and for_items and not against_items:
        flags.append("verdict_contradicts_evidence")
    why = _clip(verdict.get("why"), 480)
    denial = _clip(verdict.get("denial_reason")) if supports is False else ""
    summary = why or _clip(extract.get("business_in_one_line"))
    return QualResult(
        supports_outlier=supports,
        red_flags=flags,
        kpis=kpis,
        operating_plan=_clip(extract.get("operating_plan")),
        summary=summary,
        why=why,
        evidence_quotes=quotes,
        evidence_for=for_items,
        evidence_against=against_items,
        denial_reason=denial,
    )


def catalysts(
    candidate: Candidate,
    earnings_date: str | None,
    in_window: bool,
    filing_excerpt: str,
    skip_llm: bool = False,
) -> CatalystResult:
    iso = normalize_earnings_date(earnings_date) or earnings_date
    if skip_llm or not llm_available():
        return CatalystResult(
            earnings_date=iso,
            earnings_in_window=in_window,
            tradeable=in_window,
            reason="LLM skipped; using earnings date window only",
        )
    payload = chat_json(
        f"Identify non-earnings catalysts that could change revenue or EPS expectations inside "
        f"{catalyst_window()[0]}-{catalyst_window()[1]} calendar days. "
        "Each catalyst must be a dated event, not a news headline or financial-table dump. "
        "If none, return an empty list. Do not invent events that are not in the research pack. "
        + JSON_HINT,
        "Return JSON keys: non_earnings (array of {event, date: YYYY-MM-DD, why}), meaningful (bool), reason (string).\n"
        f"Side={candidate.side.value} ticker={candidate.ticker} earnings_date={iso} in_window={in_window}\n"
        f"Excerpt:\n{filing_excerpt[:8000]}",
    )
    non = filter_non_earnings(payload.get("non_earnings") or [])
    meaningful = bool(payload.get("meaningful")) and bool(non)
    tradeable = bool(in_window or (meaningful and non))
    return CatalystResult(
        earnings_date=iso,
        earnings_in_window=in_window,
        non_earnings=non,
        tradeable=tradeable,
        reason=str(payload.get("reason") or ""),
    )



def _evidence_block(qual: QualResult) -> list[str]:
    """Weighted evidence, so the conviction score is legible in the markdown."""
    from ptm.ranking import conviction_detail

    detail = conviction_detail(qual)
    if not detail["for"] and not detail["against"]:
        return []
    lines = [
        f"**Conviction {detail['score']:+.2f}**  "
        f"(for {detail['for_total']:.2f} / against {detail['against_total']:.2f}; "
        f"{detail['quantified_items']} of {len(detail['for']) + len(detail['against'])} quantified)",
        "",
        "| | Reason | Magnitude | Weight |",
        "|---|---|---|---|",
    ]
    for side, rows in (("for", detail["for"]), ("against", detail["against"])):
        for row in rows:
            mag = (
                f"{row['impact_pct']:+.1f}% {row['impact_on']}"
                if row["quantified"]
                else "not quantified"
            )
            lines.append(f"| {side} | {str(row['claim']).replace('|', '/')} | {mag} | {row['weight']:.2f} |")
    for flag in detail["penalties"]:
        lines.append(f"| penalty | {flag} | | -{1.0:.2f} |")
    lines.append("")
    return lines


def _earnings_block(earnings) -> list[str]:
    """Lines describing when the name reports, flagging a projected date."""
    if earnings is None:
        return ["Next earnings: unknown"]
    if not earnings.estimated:
        return [
            f"Next earnings: {earnings.date} (published), "
            f"{earnings.days_to_earnings} calendar days out"
        ]
    return [
        f"Next earnings: **{earnings.date} (estimated, not published)**, "
        f"{earnings.days_to_earnings} calendar days out",
        f"- {earnings.basis}",
        "- Filed under this window on that estimate; the catalyst gate used the published date only.",
    ]


def fallback_template(
    candidate: Candidate,
    qual: QualResult,
    cats: CatalystResult,
    timing_comment: str,
    prm: dict,
    earnings=None,
) -> str:
    side = "LONG" if candidate.side == Side.LONG else "SHORT"
    return "\n".join(
        [
            f"# {side} {candidate.ticker} — {candidate.name}",
            "",
            f"Sector: {candidate.sector}  ",
            f"EG case: {candidate.eg_case}  ",
            f"Price: {candidate.price}  Mcap: {candidate.market_cap}",
            f"PE1 {candidate.pe1} vs sector {candidate.sector_pe1}  EG1 {candidate.eg1}",
            "",
            "## Qualitative",
            qual.why or qual.summary or "n/a",
            "",
            *_evidence_block(qual),
            *([f"- {q}" for q in (qual.evidence_quotes or [])[:3]]),
            "",
            "## Catalysts",
            *_earnings_block(earnings),
            f"Earnings inside the {catalyst_window()[0]}-{catalyst_window()[1]} day catalyst window: "
            f"{cats.earnings_in_window}",
            *([f"- {item}" for item in cats.non_earnings] or ["- none identified"]),
            "",
            "## Risk footnote (not a gate)",
            json.dumps(prm, default=str) if prm else "n/a",
        ]
    )


_fallback_template = fallback_template


def _markdown_usable(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    return not stripped.startswith("{") and not stripped.startswith("[")


def render_template(
    candidate: Candidate,
    qual: QualResult,
    cats: CatalystResult,
    timing_comment: str,
    prm: dict,
    skip_llm: bool = False,
    earnings=None,
) -> str:
    fallback = fallback_template(candidate, qual, cats, timing_comment, prm, earnings)
    if skip_llm or not llm_available():
        return fallback
    try:
        payload = chat_json(
            "Fill a PTM trade idea template in Markdown. Be concise. Do not invent numbers. "
            "Never mention price action, charts, momentum, moving averages, MACD or any other "
            "technical-analysis entry signal: this process excludes them. " + JSON_HINT,
            "Return JSON {markdown: string} covering: 1 quant 2 sector 3 qualitative (use qual.why) "
            "4 catalysts 5 optional ATR risk footnote only.\n"
            "If EARNINGS.estimated is true, the catalysts section MUST say that no future earnings "
            "date was published, quote EARNINGS.basis, and mark the date as estimated.\n"
            f"{candidate.model_dump_json()}\nQUAL:{qual.model_dump_json()}\nCAT:{cats.model_dump_json()}\n"
            f"EARNINGS:{earnings.model_dump_json() if earnings is not None else '{}'}\n"
            f"PRM:{json.dumps(prm)}",
        )
        markdown = str(payload.get("markdown") or "")
        if _markdown_usable(markdown):
            return markdown
    except Exception:
        return fallback
    return fallback
