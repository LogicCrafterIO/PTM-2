from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from openai import OpenAI

from ptm.config import data_dir, env, toml_settings
from ptm.io import write_json
from ptm.models import Candidate, CatalystResult, MacroSnapshot, QualResult, Side
from ptm.timing_prm import earnings_in_window, normalize_earnings_date

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


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*)\n```$", text, flags=re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    cleaned = "".join(ch if (ch >= " " or ch in "\n\t\r") else " " for ch in text)
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{", cleaned)
    if not match:
        raise json.JSONDecodeError("No JSON object", cleaned, 0)
    payload, _ = json.JSONDecoder().raw_decode(cleaned[match.start() :])
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("JSON root is not an object", cleaned, 0)
    return payload


FALLBACK_MODELS = [
    "meta/llama-3.1-8b-instruct",
]


def chat_json(system: str, user: str) -> dict:
    cfg = toml_settings()["llm"]
    log_dir = data_dir("llm_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    last_error = None
    models = [model_name()] + [m for m in FALLBACK_MODELS if m != model_name()]
    content = "{}"
    used = model_name()
    for used in models:
        try:
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
            continue
    if last_error and content == "{}":
        raise last_error
    write_json(
        log_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json",
        {"model": used, "system": system, "user": user[:4000], "content": content},
    )
    return _extract_json(content)


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


def filter_non_earnings(raw_items: list | None, low_days: int = 20, high_days: int = 60) -> list[str]:
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
    system = (
        "You are doing PTM qualitative processing. Infer KPIs and the management operating plan "
        "ONLY from the research pack. Decide if that evidence supports or denies the quantitative "
        "outlier (premium longs / discount shorts). A good company is not automatically a good trade. "
        "A Yahoo business summary, news headlines, 8-K text, MD&A, and ISM comments ARE valid sources. "
        "Extract operating KPIs (segments, products, backlog, utilization, volumes, pricing). "
        "Do NOT list statement line items as KPIs (revenue, net_income, ebit, cash, debt, assets, equity, interest). "
        "Infer the management operating plan from those sources. "
        "Set supports_outlier to null ONLY if there is no business description and no headlines. "
        + JSON_HINT
    )
    user = (
        "Return JSON keys: supports_outlier (bool or null), red_flags (string[]), kpis (string[]), "
        "operating_plan (string), summary (string).\n"
        f"Candidate:\n{candidate.model_dump_json()}\n\nResearch pack:\n"
        f"{filing_excerpt[: toml_settings()['llm']['max_filing_chars']]}"
    )
    payload = chat_json(system, user)
    raw = payload.get("supports_outlier")
    if (raw is None or raw == "null") and not thin:
        payload = chat_json(
            system + " A business description is present. supports_outlier must be true or false, not null. ",
            user,
        )
        raw = payload.get("supports_outlier")
    supports: bool | None
    if raw is None or raw == "null":
        supports = None
    else:
        supports = bool(raw)
    kpis, stripped = sanitize_kpis(list(payload.get("kpis") or []))
    flags = [str(x) for x in (payload.get("red_flags") or [])]
    if stripped:
        flags.append("generic_kpis_stripped")
    return QualResult(
        supports_outlier=supports,
        red_flags=flags,
        kpis=kpis,
        operating_plan=str(payload.get("operating_plan") or ""),
        summary=str(payload.get("summary") or ""),
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
        "Identify non-earnings catalysts that could change revenue or EPS expectations inside 20-60 days. "
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


def fallback_template(candidate: Candidate, qual: QualResult, cats: CatalystResult, timing_comment: str, prm: dict) -> str:
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
            qual.summary or "n/a",
            "",
            "## Catalysts",
            f"Earnings: {cats.earnings_date} in_window={cats.earnings_in_window}",
            *([f"- {item}" for item in cats.non_earnings] or ["- none identified"]),
            "",
            "## Timing / PRM",
            timing_comment,
            json.dumps(prm, default=str),
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
) -> str:
    fallback = fallback_template(candidate, qual, cats, timing_comment, prm)
    if skip_llm or not llm_available():
        return fallback
    try:
        payload = chat_json(
            "Fill a PTM trade idea template in Markdown. Be concise. Do not invent numbers. " + JSON_HINT,
            "Return JSON {markdown: string} covering: 1 quant 2 sector 3 qualitative 4 catalysts 5 timing/structure.\n"
            f"{candidate.model_dump_json()}\nQUAL:{qual.model_dump_json()}\nCAT:{cats.model_dump_json()}\n"
            f"TIMING:{timing_comment}\nPRM:{json.dumps(prm)}",
        )
        markdown = str(payload.get("markdown") or "")
        if _markdown_usable(markdown):
            return markdown
    except Exception:
        return fallback
    return fallback
