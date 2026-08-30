from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timezone
from threading import Lock

from openai import OpenAI

from ptm.config import data_dir, env, llm_limits, toml_settings
from ptm.io import write_json
from ptm.log import log
from ptm.models import Candidate, CatalystResult, EvidenceItem, MacroSnapshot, QualResult, Side
from ptm.risk import catalyst_window, earnings_in_window, normalize_earnings_date
from ptm.themes import labels as theme_labels
from ptm.themes import prompt_block as theme_prompt_block

JSON_HINT = "Reply with a single JSON object only. No markdown."
GENERIC_KPIS = {"revenue", "net_income", "ebit", "cash", "debt", "assets", "equity", "interest"}
OPERATING_KPI_RE = re.compile(
    r"\b(backlog|bookings?|orders?|volume|utili[sz]ation|margin|pricing|capacity|"
    r"subscribers?|customers?|units?|stores?|locations?|market share|retention|"
    r"guidance|pipeline|procedures?|shipments?|inventory|same-store|comparable sales)\b",
    re.I,
)
MISSION_PLAN_RE = re.compile(
    r"^(?:our mission|our vision|to be the|enabl(?:e|ing) a|empower(?:ing)?|"
    r"focused on delivering|lead(?:ing)? the)\b",
    re.I,
)
HEADLINE_RE = re.compile(r"\?$|outpaced|do options traders|what to expect", re.I)


def _active_provider() -> str:
    settings = env()
    if settings.ollama_api_key:
        return "ollama"
    if settings.nvidia_api_key:
        return "nvidia"
    if settings.openai_api_key:
        return "openai"
    return "none"


def llm_available() -> bool:
    return _active_provider() in {"ollama", "nvidia", "openai"}


def client() -> OpenAI:
    settings = env()
    provider = _active_provider()
    if provider == "ollama":
        # Ollama Cloud is OpenAI-compatible. Larger output budgets and context
        # windows than NVIDIA's hosted endpoints, so truncation verdict errors
        # should drop once the larger model is selected.
        return OpenAI(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            timeout=120.0,
        )
    if provider == "nvidia":
        # 45s was enough until the verdict prompt grew to carry sized facts and
        # expectations. On the larger prompt the 49B exceeded it often enough
        # that 47 of 195 verdicts (24%) silently fell through to the 8B
        # fallback - a quiet model downgrade is worse than a slow run.
        return OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key, timeout=120.0)
    if provider == "openai":
        return OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key, timeout=90.0)
    raise RuntimeError("No LLM API key set")


def model_name() -> str:
    settings = env()
    provider = _active_provider()
    if provider == "ollama":
        return settings.ollama_model
    if provider == "nvidia":
        return settings.nvidia_model
    return settings.openai_model


def _max_tokens() -> int:
    return int(llm_limits()["max_tokens"])


TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
# Loose fence: models wrap JSON in markdown even when told not to, and a
# truncated reply often opens ```json without closing it.
FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)(?:\n```|\Z)", re.S | re.I)


def _repair_json(text: str) -> str | None:
    """Fix the syntax error small models actually make.

    A trailing comma before a closing brace or bracket accounted for every JSON
    failure observed across a 308-name run (~2% of calls). Losing an idea's
    catalysts to a stray character is not a fair trade.
    """
    repaired = TRAILING_COMMA_RE.sub(r"\1", text)
    return repaired if repaired != text else None


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    fence = FENCE_RE.search(text)
    return fence.group(1).strip() if fence else text


def _as_object(text: str) -> dict | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _salvage_truncated(text: str) -> str | None:
    """Close a truncated JSON object so a usable prefix can still parse.

    Measured on a live run: 5 of 15 verdicts were cut mid-object. Keys are
    requested with filing_direction / supports_outlier first, so recovering the
    prefix is enough to gate the idea even if evidence_for was chopped.
    """
    match = re.search(r"\{", text)
    if not match:
        return None
    raw = text[match.start() :]
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in raw:
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    out = raw
    if escape:
        out = out[:-1]
    if in_string:
        out += '"'
    out = TRAILING_COMMA_RE.sub(r"\1", out)
    if re.search(r',\s*"[^"\\]*"\s*:\s*$', out):
        out = re.sub(r',\s*"[^"\\]*"\s*:\s*$', "", out)
    elif re.search(r'"[^"\\]*"\s*:\s*$', out):
        out += " null"
    out = re.sub(r',\s*"[^"\\]*"\s*$', "", out)
    out = re.sub(r',\s*$', "", out)
    while stack:
        out += stack.pop()
    return TRAILING_COMMA_RE.sub(r"\1", out)


def _extract_json(text: str) -> dict:
    cleaned = "".join(ch if (ch >= " " or ch in "\n\t\r") else " " for ch in _strip_fences(text))
    for attempt in (cleaned, _repair_json(cleaned)):
        if attempt is None:
            continue
        payload = _as_object(attempt)
        if payload is not None:
            return payload
    match = re.search(r"\{", cleaned)
    if not match:
        raise json.JSONDecodeError("No JSON object", cleaned, 0)
    tail = cleaned[match.start() :]
    for attempt in (tail, _repair_json(tail)):
        if not attempt:
            continue
        try:
            payload, _ = json.JSONDecoder().raw_decode(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    salvaged = _salvage_truncated(cleaned)
    if salvaged:
        payload = _as_object(salvaged)
        if payload is not None:
            return payload
        try:
            payload, _ = json.JSONDecoder().raw_decode(salvaged)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
    raise json.JSONDecodeError("No JSON object", cleaned, 0)




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
# Usage/credit exhaustion, which is NOT a momentary throttle: seconds-scale
# backoff cannot clear it and falling back to a smaller model shares the same
# key, so it would hit the same wall. Callers that want to outlast one must
# wait on the order of minutes - the dive retry ladder does, chat_json does not.
_QUOTA_MARKERS = (
    "402",
    "payment required",
    "insufficient credit",
    "out of credit",
    "credit balance",
    "quota exceeded",
    "usage limit",
    "billing",
)


def is_quota_text(text: str) -> bool:
    lowered = (text or "").lower()
    if re.search(r"\b402\b", lowered):
        return True
    return any(marker in lowered for marker in _QUOTA_MARKERS if not marker.isdigit())


# A provider 429 ("too many requests") is not the same as used-up quota, but it
# is equally useless to hammer: the dive ladder must wait minutes, and two
# consecutive rate-limited dives mean the whole run is throttled. Kept separate
# from is_quota_* on purpose — inside chat_json a 429 still gets its own
# second-scale backoff and fallback-model path; only the dive ladder and the
# run-level breaker treat it as pause-worthy.
_RATE_LIMIT_MARKERS = (
    "429",
    "rate-limited",
    "rate limited",
    "rate limit",
    "too many requests",
)


def is_rate_limited(exc_or_text) -> bool:
    """HTTP 429 / throttle-shaped: wait minutes, don't slam again."""
    text = str(getattr(exc_or_text, "response", None) and getattr(exc_or_text, "response").text or exc_or_text)
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


def is_quota_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status == 402:
        return True
    return is_quota_text(str(exc))


def _is_throttled(exc: Exception) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status in {429, 502, 503}:
        return True
    return any(marker in text for marker in _THROTTLE_MARKERS)


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return True
    return False


def _fallback_models(primary: str) -> list[str]:
    """Provider-aware fallbacks. Only NVIDIA has a known smaller fallback here."""
    if _active_provider() == "nvidia":
        return [m for m in ["meta/llama-3.1-8b-instruct"] if m != primary]
    return []


def _shorten_middle(text: str, limit: int) -> str:
    """Trim from the MIDDLE, keeping both ends.

    The retry path used to keep only the first 4000 characters. The verdict
    question appends the expectations and theme blocks at the end, so a retry
    silently discarded exactly the context the retry was meant to help with -
    and the JSON keys are declared at the start, so cutting either end loses
    something load-bearing.
    """
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head - 40
    return text[:head] + "\n...[trimmed for retry]...\n" + text[-tail:]


def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    used_out: list[str] | None = None,
    allow_fallback: bool = True,
    _retried: bool = False,
) -> dict:
    """Chat completion returning parsed JSON.

    `used_out`, if given, receives the model that actually answered.
    FALLBACK_MODELS means a pinned model can quietly be replaced by a smaller
    one - on a first run of the 70B, 9 of 12 verdicts silently came back from
    the 8B. A caller that pins a model for a reason needs to know when that did
    not happen. Truncated replies from the pinned model are salvaged locally
    before any fallback; a timeout on the pinned model is retried once on that
    same model before the 8B is tried.
    """
    cfg = toml_settings()["llm"]
    log_dir = data_dir("llm_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    last_error = None
    primary = model or model_name()
    models = [primary]
    if allow_fallback:
        models = [primary] + _fallback_models(primary)
    content = "{}"
    used = primary
    finish_reason = ""
    quota_dead = False
    for used in models:
        timeout_tries = 0
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
                    max_tokens=_max_tokens(),
                )
                choice = response.choices[0]
                content = choice.message.content or "{}"
                finish_reason = str(getattr(choice, "finish_reason", None) or "")
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                # Usage/credit exhaustion does not clear on seconds-scale
                # backoff, and every fallback model shares the same key, so
                # trying them just burns more quota. Raise out of chat_json
                # now; the dive retry ladder owns minute-scale waits for this.
                if is_quota_error(exc):
                    quota_dead = True
                    break
                # Running ideas concurrently makes 429s routine rather than
                # exceptional. Without this an idea silently lost its catalysts
                # to a transient throttle, which reads identically to "no
                # catalysts found". Back off and retry before giving up.
                if _is_throttled(exc) and attempt < RATE_LIMIT_RETRIES - 1:
                    delay = RATE_LIMIT_BACKOFF * (2**attempt) + random.uniform(0, 0.4)
                    log(f"llm: throttled, retrying in {delay:.1f}s ({attempt + 1}/{RATE_LIMIT_RETRIES - 1})")
                    time.sleep(delay)
                    continue
                # A truncated 49B answer is still that model's answer. A timeout
                # is not a reason to silently swap in the 8B; retry the pin once.
                if used == primary and _is_timeout(exc) and timeout_tries < 1:
                    timeout_tries += 1
                    log(f"llm: timeout on {used}, retrying pinned model once")
                    continue
                break
        if quota_dead or last_error is None:
            break
    if last_error and content == "{}":
        raise last_error
    write_json(
        # Microseconds: five concurrent idea workers fire several calls per
        # second, and a second-resolution stamp silently lost all but one of
        # a same-second burst of debug logs.
        log_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json",
        {
            "model": used,
            "finish_reason": finish_reason,
            "system": system,
            "user": user[:4000],
            "content": content,
        },
    )
    if used_out is not None:
        used_out.append(used)
    try:
        return _extract_json(content)
    except json.JSONDecodeError:
        if _retried:
            raise
        # Truncation is a length problem, not a "wrong model" problem. Retry
        # the pin with a shorter ask; do not fall through to the 8B for this.
        pinned_only = finish_reason == "length" or used == primary
        return chat_json(
            system + " Return a smaller JSON object. Keep every string under 240 characters. Close all quotes.",
            _shorten_middle(user, 4000),
            model=primary if pinned_only else model,
            used_out=used_out,
            allow_fallback=False if pinned_only else allow_fallback,
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


SCREEN_EVIDENCE_RE = re.compile(
    r"\b(consensus|fy1|fy2|forward eps|p/?e|peg|relative valuation|sector multiple|eg case)\b",
    re.I,
)


def _strip_screen_evidence(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], int]:
    """Remove circular evidence copied from the quantitative candidate screen."""
    kept = [
        item
        for item in items
        if not SCREEN_EVIDENCE_RE.search(f"{item.claim} {item.metric}")
    ]
    return kept, len(items) - len(kept)


def verdict_model() -> str:
    """Model for the qualitative verdict, which may differ from the default.

    This is the single call the book depends on: everything upstream of it is
    deterministic, and it alone decides which names survive. It is also the step
    where a small model demonstrably failed - returning a boolean that
    contradicted its own stated evidence. One call per name makes a larger model
    cheap insurance. Extraction and templating stay on the default.

    When Ollama Cloud is configured it takes precedence so the larger verdict
    model is used; otherwise the legacy TOML setting is honoured.
    """
    settings = env()
    if settings.ollama_api_key and settings.ollama_verdict_model:
        return settings.ollama_verdict_model
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


# A figure attached to a unit. Levels and changes both qualify; the verdict
# prompt is what teaches the model to tell them apart.
FIGURE_RE = re.compile(r"\d[\d,.]*\s*(?:%|percent|bps|basis points|million|billion)", re.I)
# Period-over-period language. These sentences are worth more than levels,
# because impact_pct is defined as a CHANGE and a level cannot size one.
CHANGE_WORDS_RE = re.compile(
    r"\b(grew|growth|increased|decreased|declined|decline|rose|fell|up|down|expanded|"
    r"improved|accelerat\w+|versus|compared|year[- ]over[- ]year|yoy|sequential\w*)\b",
    re.I,
)
# The parenthetical the pack puts in front of its REPORTED CHANGES bullets. It
# is an instruction to the model, sitting immediately before real figures.
PACK_INSTRUCTION_RE = re.compile(r"\(computed from[^)]*\):", re.I)

# Language that describes the FUTURE rather than the quarter just closed. This
# distinction turned out to be the whole game. Ranking "changes" ahead of
# "levels" was right as far as it went, but a change is still backward-looking -
# and the verdict was then comparing last quarter's realised growth against a
# forward consensus, which is a category error. A company that grew 51.7% last
# quarter against a forward consensus of +46.5% is not evidence the market is
# wrong; the consensus may be correctly pricing a deceleration.
#
# What actually bears on a coming print: the company's own guidance (especially
# a raise), contracted future revenue (backlog, bookings, RPO, ARR), order
# intake, and explicit outlook statements.
# Longest sentence still considered a fact, and the length each is clipped to.
# Guidance and outlook sentences pack several figures into one long clause, so a
# tight cap discards them preferentially.
MAX_FACT_CHARS = 460
FACT_CLIP_CHARS = 300

FORWARD_RE = re.compile(
    r"\b(guidance|guides?|guided|outlook|expects?|expected|anticipat\w+|forecast\w*|"
    r"full[- ]year|next (?:quarter|year)|fiscal 20\d\d|FY ?20\d\d|backlog|bookings|"
    r"remaining performance obligation|RPO|ARR|annual recurring|order intake|new orders|"
    r"pipeline|raised|raising|reaffirm\w+|reiterat\w+|target\w*|will be|plans to)\b",
    re.I,
)


def _sized_facts(pack: str, limit: int = 28) -> list[str]:
    """Sentences from the research pack that actually carry a figure.

    The verdict pass never saw the pack. It received only the extract model's
    ~1.5KB summary, while its own system prompt instructed it to "search the
    pack for the number that sizes it" - asking a model to find numbers in a
    document it was never given. That is the mechanical reason most evidence
    came back unquantified, and no amount of prompt tuning could fix it.

    Ordering, and each tier is tagged so the verdict can tell them apart:

    1. ``[FORWARD]`` - guidance, backlog, bookings, order intake, outlook. The
       only tier that bears directly on a coming print, and the scarcest.
    2. ``[REPORTED]`` - realised period-over-period changes, including the
       pack's own pre-computed block. Sizeable, but describes a quarter already
       closed and already in consensus.
    3. ``[LEVEL]`` - standing figures, which cannot size a change at all.

    Changes used to lead. That was a mistake: it let the verdict compare last
    quarter's realised growth against a forward consensus and call the
    difference a mispricing, when the consensus may simply be pricing a
    deceleration correctly.
    """
    text = " ".join((pack or "").split())
    if not text:
        return []
    # The pack labels its own REPORTED CHANGES block with an instruction to the
    # model. That sentence sits directly in front of figures, so the scan below
    # picked it up and offered the instruction back as though it were a fact.
    text = PACK_INSTRUCTION_RE.sub("", text)
    leading: list[str] = []
    marker = "REPORTED CHANGES"
    if marker in text:
        tail = text.split(marker, 1)[1]
        # The block runs to the next ALL-CAPS section label in _pack_text.
        stop = re.search(r"(ITEM 1 BUSINESS|MD&A|8-K EX-99\.1|NEWS|ISM):", tail)
        block = tail[: stop.start()] if stop else tail[:1200]
        # Whitespace is already normalised, so the block's newline-indented
        # bullets have collapsed to " - ".
        leading = [
            f"[REPORTED] {part.strip(' -:')}"
            for part in block.split(" - ")
            if FIGURE_RE.search(part)
        ]
    forward, changes, levels, seen = [], [], [], set()
    for sentence in re.split(r"(?<=[.;])\s+", text):
        sentence = sentence.strip()
        # The upper bound was 240 and it was quietly discarding the best
        # evidence in the pack. Guidance sentences are long *because* they are
        # dense with figures - SEZL's two guidance lines ran 352 and 250
        # characters, so a raise to FY2026 guidance, the single strongest signal
        # available for that name, was filtered out while a standing balance
        # figure got through. Keep the sentence and truncate it instead.
        if not (12 < len(sentence) <= MAX_FACT_CHARS) or not FIGURE_RE.search(sentence):
            continue
        sentence = sentence[:FACT_CLIP_CHARS]
        key = sentence.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        # Forward first. These are scarce - median 1 numeric forward-looking
        # sentence per pack, and 67 of 200 packs have none - so a budget that
        # spends itself on realised changes will simply never show the model the
        # guidance raise sitting further down the exhibit.
        if FORWARD_RE.search(sentence):
            forward.append(f"[FORWARD] {sentence}")
        elif CHANGE_WORDS_RE.search(sentence):
            changes.append(f"[REPORTED] {sentence}")
        else:
            levels.append(f"[LEVEL] {sentence}")
    out: list[str] = []
    for item in forward + leading + changes + levels:
        if item and item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def sanitize_kpis(kpis: list | None) -> tuple[list[str], bool]:
    cleaned: list[str] = []
    stripped = False
    for raw in kpis or []:
        token = str(raw).strip()
        key = token.lower().replace(" ", "_")
        if key in GENERIC_KPIS or token.lower() in GENERIC_KPIS:
            stripped = True
            continue
        if token and (FIGURE_RE.search(token) or OPERATING_KPI_RE.search(token)):
            cleaned.append(token)
        elif token:
            stripped = True
    return cleaned, stripped


def sanitize_operating_plan(value: object) -> tuple[str, bool]:
    """Drop mission statements that do not describe a forward operating action."""
    plan = _clip(value)
    if plan and MISSION_PLAN_RE.search(plan):
        return "", True
    return plan, False


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


# The model's ONE job on the expectation gap: which way do the filings point?
# Asking for a percentage produced round-number clustering (8.5/10/12/15) and
# constant "medium" confidence, because backing out a consensus-implied growth
# rate is arithmetic a mid-sized model cannot do. Classification it can do.
# The magnitude comes from measured analyst revisions instead - see ptm/drift.py.
_DIRECTION_RULE = (
    "FINALLY, one classification - and it is the most important field you return. Do NOT try to "
    "estimate an EPS surprise percentage; you are not given enough to compute one and a guessed "
    "figure is worse than none. Instead answer a simpler question.\n"
    "Set filing_direction to what THIS company's own filings say about where its earnings are "
    "heading:\n"
    "  improving      - the forward evidence points to earnings ahead of where they have been\n"
    "  deteriorating  - the forward evidence points to earnings falling short\n"
    "  mixed          - genuinely two-sided\n"
    "  silent         - the filings do not address direction\n"
    "Weigh the [FORWARD] facts most heavily: guidance, backlog, bookings, order intake, outlook. "
    "A [REPORTED] figure describes a quarter that has already closed and that analysts have "
    "already seen, so it is weak evidence about what comes next - do not treat last quarter's "
    "growth rate as a forecast.\n"
    "Set direction_basis to the specific figures behind that call, naming whether each is forward "
    "or reported. Judge the company, NOT the trade: a short whose filings are improving must be "
    "reported as improving. The magnitude of any mispricing is computed elsewhere from measured "
    "analyst revisions, and your direction is what decides whether those revisions are supported. "
    "Getting the direction right matters more than making it agree with the side. "
)

FILING_DIRECTIONS = {"improving", "deteriorating", "mixed", "silent"}


# How much of the move is left. The screen returns quantitative outliers, so a
# re-rating has usually already begun by the time a name arrives here - which
# makes durability the live question rather than direction alone. A model
# cannot measure this, but it can read a filing for the difference between
# guidance raised again and guidance merely reaffirmed.
_DURABILITY_RULE = (
    "AND one more classification. The screen that produced this name selects quantitative "
    "OUTLIERS on P/E, PEG and earnings growth, so any re-rating has usually already STARTED. "
    "The live question is not whether it has begun but how much is left.\n"
    "Set momentum_durability from the filings:\n"
    "  building   - the drivers are still strengthening: guidance raised again, backlog "
    "still growing, orders accelerating, new capacity or pricing coming\n"
    "  intact     - the drivers are in place and steady\n"
    "  fading     - comparatives are getting harder, guidance merely reaffirmed rather than "
    "raised, backlog flat, a one-off benefit about to lap\n"
    "  exhausted  - the drivers have run their course, or peak margins and capacity limits "
    "cap what is left\n"
    "  unclear    - the filings do not say\n"
    "Set durability_basis to the specific evidence, and prefer [FORWARD] facts: whether "
    "guidance was RAISED or merely held is the single most useful distinction here. Do not "
    "infer durability from how large the past growth was - a big number that is about to lap "
    "is fading, not building. If a global theme you were shown is the driver, say which. "
)

DURABILITY_VALUES = {"building", "intact", "fading", "exhausted", "unclear"}


def _durability(verdict: dict) -> str:
    """How much of the run is left, defaulted to unclear when unrecognised."""
    value = str(verdict.get("momentum_durability") or "").strip().lower()
    return value if value in DURABILITY_VALUES else "unclear"


def _filing_direction(verdict: dict) -> str:
    """The verdict's read on where earnings are heading, defaulted safely.

    An unrecognised answer becomes "silent" rather than being guessed at: a
    wrong direction does not merely mis-size the gap, it inverts its sign.
    """
    value = str(verdict.get("filing_direction") or "").strip().lower()
    return value if value in FILING_DIRECTIONS else "silent"


def qualitative(
    candidate: Candidate,
    filing_excerpt: str,
    thin: bool = False,
    skip_llm: bool = False,
    expectations: dict | None = None,
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
    pack = filing_excerpt[: int(llm_limits()["max_filing_chars"])]
    extract_system = (
        "Extract operating facts from the research pack. Do not decide if this is a trade. "
        "A Yahoo summary, headlines, 8-K, MD&A, and ISM comments ARE valid sources. "
        "KPIs must be measurable forward operating drivers (backlog, bookings, orders, utilization, "
        "volumes, pricing, capacity, customer or unit counts, guidance), not product/category names "
        "and not statement lines (revenue, net_income, ebit, cash, debt). "
        "operating_plan must name a concrete forward action such as capacity expansion, a launch, "
        "cost reduction or channel build. Return an empty string for a mission statement or slogan. "
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
    operating_plan, plan_stripped = sanitize_operating_plan(extract.get("operating_plan"))
    flags = [str(x) for x in (extract.get("red_flags") or [])]
    quotes = [_clip(q, 200) for q in (extract.get("quotes") or []) if str(q).strip()][:4]
    if stripped:
        flags.append("generic_kpis_stripped")
    if plan_stripped:
        flags.append("mission_statement_plan_stripped")
    extract_summary = {
        "business": _clip(extract.get("business_in_one_line")),
        "operating_plan": operating_plan,
        "kpis": kpis,
        "ism_link": _clip(extract.get("ism_link")),
        "red_flags": flags,
        "quotes": quotes,
        # Straight from the pack, not from the extract model: pass A summarises
        # and in doing so drops the figures pass B is required to cite.
        "reported_figures": _sized_facts(pack),
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
        "Evidence_for and evidence_against must come from company-reported operating facts. "
        "Never cite consensus FY1/FY2 EPS growth, P/E, PEG, relative valuation, the EG case, or "
        "any other quantitative-screen input as qualitative evidence; those facts created the "
        "candidate and cannot independently confirm it. "
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
        + _DIRECTION_RULE
        + _DURABILITY_RULE
        + "Keep every string under 240 characters. " + JSON_HINT
    )
    ratio = ""
    if candidate.pe1 and candidate.sector_pe1:
        ratio = f" ({candidate.pe1 / candidate.sector_pe1:.1f}x sector)"
    industry_bit = ""
    if candidate.pe1 and candidate.industry_pe1:
        industry_bit = f" vs industry {candidate.industry_pe1} ({candidate.pe1 / candidate.industry_pe1:.1f}x)"
    ask = (
        "does the evidence justify PAYING this premium?"
        if candidate.side == Side.LONG
        else "does the evidence show this discount is DESERVED?"
    )
    verdict_user = (
        "Return JSON keys, IN THIS ORDER - the first four decide whether this idea is used "
        "at all, so answer them even if you must keep everything else short: "
        "filing_direction (improving|deteriorating|mixed|silent), direction_basis (string), "
        "momentum_durability (building|intact|fading|exhausted|unclear), durability_basis "
        "(string), supports_outlier (bool), why (string, 2-4 sentences), denial_reason "
        "(string), evidence_for (array of {claim, metric, impact_pct, impact_on, quantified}, "
        "at most 4), evidence_against (same shape, at most 4).\n"
        f"Side={candidate.side.value}. P/E {candidate.pe1} vs sector {candidate.sector_pe1}{ratio}"
        f"{industry_bit}. "
        f"EG case={candidate.eg_case}.\n"
        f"CONSENSUS THE MARKET IS HOLDING: FY1 EPS {candidate.eps1}"
        + (
            f", which is {candidate.eg1 * 100:+.1f}% on last year's {candidate.eps0}"
            if candidate.eg1 is not None
            else ""
        )
        + ".\n"
        f"Question: {ask}\n\n"
        f"Extract:\n{json.dumps(extract_summary, default=str)}"
        + theme_prompt_block(pack)
    )
    verdict: dict = {}
    wanted_model = verdict_model()
    answered_by: list[str] = []

    def _deny_verdict(reason: str) -> QualResult | dict:
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
        flags.append("llm_json_failed_verdict")
        return {
            "supports_outlier": False,
            "why": "Verdict JSON failed after a usable extract; not treating as a pass.",
            "denial_reason": _clip(reason, 240),
        }

    try:
        verdict = chat_json(verdict_system, verdict_user, model=wanted_model, used_out=answered_by)
        if answered_by and answered_by[0] != wanted_model:
            # The gate ran on something smaller than intended. Say so on the idea.
            flags.append(f"verdict_model_downgraded_to_{answered_by[0]}")
    except json.JSONDecodeError as exc:
        failed = _deny_verdict(f"verdict JSON unreadable: {exc.msg}")
        if isinstance(failed, QualResult):
            return failed
        verdict = failed
    except Exception as exc:
        # Transport failure is not a parse failure. Retry the pinned verdict
        # model once more rather than treating a timeout as unreadable JSON.
        try:
            verdict = chat_json(
                verdict_system,
                verdict_user,
                model=wanted_model,
                used_out=answered_by,
                allow_fallback=False,
            )
            if answered_by and answered_by[0] != wanted_model:
                flags.append(f"verdict_model_downgraded_to_{answered_by[0]}")
        except json.JSONDecodeError as parse_exc:
            failed = _deny_verdict(f"verdict JSON unreadable: {parse_exc.msg}")
            if isinstance(failed, QualResult):
                return failed
            verdict = failed
        except Exception as retry_exc:
            label = "timeout" if _is_timeout(exc) or _is_timeout(retry_exc) else "error"
            failed = _deny_verdict(f"verdict {label}: {retry_exc}")
            if isinstance(failed, QualResult):
                return failed
            verdict = failed

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
    for_items, stripped_for = _strip_screen_evidence(
        _evidence_items(verdict.get("evidence_for"))
    )
    against_items, stripped_against = _strip_screen_evidence(
        _evidence_items(verdict.get("evidence_against"))
    )
    if stripped_for or stripped_against:
        flags.append("screen_metric_evidence_stripped")
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
        operating_plan=operating_plan,
        summary=summary,
        why=why,
        evidence_quotes=quotes,
        evidence_for=for_items,
        evidence_against=against_items,
        filing_direction=_filing_direction(verdict),
        direction_basis=_clip(verdict.get("direction_basis")),
        momentum_durability=_durability(verdict),
        durability_basis=_clip(verdict.get("durability_basis")),
        themes=theme_labels(pack),
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
    reason = str(payload.get("reason") or "")
    if not non:
        reason = (
            "Earnings date is the dated catalyst; no separate non-earnings event identified."
            if in_window
            else "No dated catalyst identified inside the configured window."
        )
    return CatalystResult(
        earnings_date=iso,
        earnings_in_window=in_window,
        non_earnings=non,
        tradeable=tradeable,
        reason=reason,
    )



def _evidence_block(qual: QualResult, side: Side = Side.LONG) -> list[str]:
    """Weighted evidence, so the conviction score is legible in the markdown."""
    from ptm.ranking import conviction_detail

    detail = conviction_detail(qual, side)
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


def _relative_peg_line(candidate: Candidate) -> str:
    """State the multiple premium against the growth premium that pays for it.

    Rendered whether or not it binds: the point is that the number can be
    checked, and a name that passes at 2.9 should be as visible as one blocked
    at 3.1.
    """
    value = candidate.relative_peg
    if value is None:
        return "Relative PEG: n/a (needs pe1, sector_pe1, eg1 and sector_eg1)"
    if candidate.pe1 and candidate.sector_pe1:
        premium = f"{candidate.pe1 / candidate.sector_pe1:.1f}x the sector multiple"
    else:
        premium = "a sector premium"
    read = "growth more than covers it" if value <= 1.0 else (
        "stretched" if value <= 2.0 else "growth does not cover it"
    )
    return f"Relative PEG: {value:.2f} — pays {premium} per unit of sector growth ({read})"


def _revisions_block(expectations: dict | None) -> list[str]:
    """Measured analyst-revision context, excluding option-chain data."""
    revisions = (expectations or {}).get("revisions") or {}
    if not revisions.get("available"):
        return []
    lines = ["## Analyst revision momentum", ""]
    for days in (30, 90):
        value = revisions.get(f"change_{days}d_pct")
        if value is not None:
            lines.append(f"- Consensus FY1 EPS change over {days} days: {value:+.1f}%")
    up = revisions.get("analysts_up_30d")
    down = revisions.get("analysts_down_30d")
    if up is not None or down is not None:
        lines.append(f"- Analysts revising up/down over 30 days: {up or 0}/{down or 0}")
    return lines + [""]


def fallback_template(
    candidate: Candidate,
    qual: QualResult,
    cats: CatalystResult,
    timing_comment: str,
    earnings=None,
    expectations: dict | None = None,
) -> str:
    side = "LONG" if candidate.side == Side.LONG else "SHORT"
    return "\n".join(
        [
            f"# {side} {candidate.ticker} — {candidate.name}",
            "",
            f"Sector: {candidate.sector}  ",
            f"EG case: {candidate.eg_case}  ",
            f"Price: {candidate.price}  Mcap: {candidate.market_cap}",
            f"PE1 {candidate.pe1} vs sector {candidate.sector_pe1}"
            + (
                f" vs industry {candidate.industry_pe1}"
                if candidate.industry_pe1 is not None
                else ""
            )
            + f"  EG1 {candidate.eg1}",
            _relative_peg_line(candidate),
            "",
            "## Qualitative",
            qual.why or qual.summary or "n/a",
            "",
            *_evidence_block(qual, candidate.side),
            *([f"- {q}" for q in (qual.evidence_quotes or [])[:3]]),
            "",
            "## Catalysts",
            *_earnings_block(earnings),
            f"Earnings inside the {catalyst_window()[0]}-{catalyst_window()[1]} day catalyst window: "
            f"{cats.earnings_in_window}",
            *([f"- {item}" for item in cats.non_earnings] or ["- none identified"]),
            "",
            *_revisions_block(expectations),
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
    skip_llm: bool = False,
    earnings=None,
    expectations: dict | None = None,
) -> str:
    fallback = fallback_template(candidate, qual, cats, timing_comment, earnings, expectations)
    if skip_llm or not llm_available():
        return fallback
    try:
        payload = chat_json(
            "Fill a PTM trade idea template in Markdown. Be concise. Do not invent numbers. "
            "Never mention price action, charts, momentum, moving averages, MACD or any other "
            "technical-analysis entry signal: this process excludes them. " + JSON_HINT,
            "Return JSON {markdown: string} covering: 1 quant 2 sector 3 qualitative "
            "(use qual.why) 4 catalysts 5 analyst revision momentum from REVISIONS.\n"
            "If EARNINGS.estimated is true, the catalysts section MUST say that no future earnings "
            "date was published, quote EARNINGS.basis, and mark the date as estimated.\n"
            f"{candidate.model_dump_json()}\nQUAL:{qual.model_dump_json()}\nCAT:{cats.model_dump_json()}\n"
            f"EARNINGS:{earnings.model_dump_json() if earnings is not None else '{}'}\n"
            f"REVISIONS:{json.dumps((expectations or {}).get('revisions') or {})}",
        )
        markdown = str(payload.get("markdown") or "")
        if _markdown_usable(markdown):
            return markdown
    except Exception:
        return fallback
    return fallback
