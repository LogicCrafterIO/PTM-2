"""Orchestration for the single-ticker deep dive.

Stages: filing context → planned web research → driver identification →
bull case → bear case → per-driver debate → synthesis → catalysts.
Each stage logs and degrades gracefully; the final markdown always renders.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from ptm.config import data_dir, env
from ptm.deepsearch import analysis, macro_view
from ptm.deepsearch.models import Catalyst, DeepResult, MacroView, SourceRef
from ptm.deepsearch.research import research
from ptm.deepsearch.web import available as web_available
from ptm.io import write_json
from ptm.llm import JSON_HINT, chat_json, llm_available, verdict_model
from ptm.log import log

CATALYST_SYSTEM = (
    "You are an equity research analyst identifying upcoming catalysts for ONE company. "
    "Only include events with a plausible window (earnings dates, product launches, regulatory "
    "decisions, contract awards, investor days, litigation rulings). For each, state what happens "
    "in each outcome. " + JSON_HINT
)


def _who(name: str, ticker: str) -> str:
    return f"{name} ({ticker})" if name else ticker


def filing_context(ticker: str, max_chars: int = 6000) -> str:
    """What the company's own filings say — the grounding the web pass plans against."""
    try:
        from ptm.ingest.edgar import latest_filing_text

        return (latest_filing_text(ticker, max_chars=max_chars) or "").strip()
    except Exception as exc:
        log(f"deepsearch {ticker}: filing context unavailable ({exc})")
        return ""


def cache_path(ticker: str):
    return data_dir("raw", "deepsearch", "runs", f"{ticker}.json")


def _cache_age_days(payload: dict) -> float | None:
    """Days since the cached dive ran, from its recorded as_of date."""
    stamp = str(payload.get("as_of") or "")
    if not stamp:
        return None
    try:
        ran_on = date.fromisoformat(stamp[:10])
    except ValueError:
        return None
    return (datetime.now(timezone.utc).date() - ran_on).total_seconds() / 86400.0


def run_deep_dive(
    ticker: str,
    name: str = "",
    sector: str = "",
    industry: str = "",
    force: bool = False,
    max_queries: int | None = None,
    max_results: int | None = None,
    max_fetches: int | None = None,
    progress=None,
    max_age_days: int | None = None,
) -> DeepResult:
    """Full deep dive for one ticker. Cached unless --force.

    `progress`, when given, is called as `progress(stage, detail)` between
    stages so a caller (the viewer's batch runner) can show live state. It
    must never raise into the pipeline.

    `max_age_days`, when set, treats a cached dive older than that many days as
    a miss (an undated one too). The idea pipeline uses it so a weekly run sees
    this week's research, while the viewer's on-demand dives keep any cache.
    """

    def report(stage: str, detail: str = "") -> None:
        log(f"deepdive {ticker}: {stage}" + (f" — {detail}" if detail else ""))
        if progress is not None:
            try:
                progress(stage, detail)
            except Exception:
                pass  # progress reporting must never break the dive

    ticker = ticker.upper().strip()
    result = DeepResult(ticker=ticker, name=name, sector=sector, industry=industry)
    if not llm_available():
        result.error = "no LLM key (OLLAMA_API_KEY / NVIDIA_API_KEY / OPENAI_API_KEY)"
        return result
    if not web_available():
        result.error = "no OLLAMA_API_KEY: web search unavailable"
        return result

    cache = cache_path(ticker)
    # `force` (a redo campaign) normally ignores the cache outright — but a
    # redo must survive being INTERRUPTED and resumed: DEEPSEARCH_CACHE_FLOOR
    # (a unix timestamp) marks when the campaign started, and caches WRITTEN
    # since then are the redo's own completed work. Re-diving them on every
    # resume would throw away exactly the dives the campaign already paid for.
    floor = env().deepsearch_cache_floor
    respects_floor = floor is not None and cache.exists() and cache.stat().st_mtime >= floor
    if cache.exists() and (not force or respects_floor):
        from ptm.io import read_json

        cached = read_json(cache)
        age = _cache_age_days(cached)
        if max_age_days is None or (age is not None and age <= max_age_days):
            if force:
                report("cache hit", "redo cache (written this campaign) kept")
            else:
                report("cache hit", f"cached result loaded ({cached.get('as_of') or 'undated'})")
            return DeepResult.model_validate(cached)
        report(
            "cache stale",
            f"dive from {cached.get('as_of') or 'unknown date'} older than {max_age_days}d; rerunning",
        )

    started = datetime.now(timezone.utc)
    result.as_of = started.date().isoformat()
    report("startup", "resolving ticker and limits")
    context = filing_context(ticker)
    report("filings", f"SEC filing context loaded ({len(context)} chars)")

    # 0. Macro / ISM backdrop, read from what `ptm weekly` already curated.
    report("macro", "reading PTM dashboard state")
    macro = macro_view.build_macro_view(sector, industry)
    if not macro.available:
        log(f"deepdive {ticker}: macro view unavailable - {macro.reason}")
    else:
        report(
            "macro",
            f"backdrop ready — bias {macro.bias or '?'}, sector tilt {macro.sector_tilt or 'n/a'}",
        )
    result.macro = macro
    limits = _limits()
    max_queries = max_queries or int(limits["max_queries"])
    max_results = max_results or int(limits["max_results"])
    max_fetches = max_fetches or int(limits["max_fetches"])

    # 1. Web research: plan → search → fetch → extract. A forced dive re-runs
    # the queries too; otherwise a "fresh" dive would quietly stand on the
    # cached pages from the last run.
    report("research", "planning web queries")
    research_out = research(
        ticker,
        name,
        context,
        max_queries=max_queries,
        max_results=max_results,
        max_fetches=max_fetches,
        progress=report,
        use_cache=not force,
    )
    result.research = research_out
    result.research.as_of = result.as_of
    findings = [f.model_dump() for f in research_out.findings]
    if not findings:
        result.error = research_out.error or "no findings from web research"
        log(f"deepdive {ticker}: FAIL {result.error}")
        report("fail", result.error)
        return result

    who = _who(name, ticker)
    report(
        "research",
        f"web research done — {len(research_out.queries_run)} queries, "
        f"{len(findings)} findings, {len(research_out.fetched_pages)} pages fetched",
    )

    who = _who(name, ticker)

    # 2. Macro transmission into this company's fundamentals (own LLM pass),
    # then the backdrop block shared with every analysis prompt.
    macro_block = ""
    if macro.available:
        report("macro-impact", "mapping backdrop onto fundamentals")
        try:
            macro = macro_view.llm_impact(macro, findings, context, who, sector)
        except Exception as exc:
            log(f"deepdive {ticker}: macro transmission FAIL {exc}")
        macro_block = macro_view.prompt_block(macro)
        if macro.narrative:
            macro_block += f"\n- Analyst read on transmission into {who}: {macro.narrative}"
    result.macro = macro

    # 3. Drivers
    report("drivers", "identifying the drivers the thesis hinges on")
    try:
        drivers = analysis.identify_drivers(findings, context, who, macro_block=macro_block)
    except Exception as exc:
        drivers = []
        log(f"deepdive {ticker}: driver identification FAIL {exc}")
    if not drivers:
        result.error = "no drivers identified"
        report("fail", result.error)
        return result

    # 3. Bull / bear cases
    report("cases", "building bull and bear cases from the findings")
    try:
        bull = analysis.build_case(findings, context, who, "bull", macro_block=macro_block)
        bear = analysis.build_case(findings, context, who, "bear", macro_block=macro_block)
    except Exception as exc:
        bull, bear = [], []
        log(f"deepdive {ticker}: bull/bear cases FAIL {exc}")

    # 4. Debate
    report("debate", f"bull vs bear on {len(drivers)} drivers")
    debate_error = ""
    used: list[str] = []
    try:
        rounds, falsifiers, confidence, confidence_why = analysis.run_debate(
            drivers, findings, context, who, used_out=used, macro_block=macro_block
        )
    except Exception as exc:
        rounds, falsifiers, confidence, confidence_why = [], [], "low", ""
        debate_error = f"debate failed: {exc}"
        log(f"deepdive {ticker}: debate FAIL {exc}")

    # 5. Synthesis — runs on whatever the earlier stages produced
    report("synthesis", "writing the final thesis")
    try:
        thesis = analysis.synthesize(rounds, bull, bear, findings, context, who, used_out=used, macro_block=macro_block)
    except Exception as exc:
        log(f"deepdive {ticker}: synthesis FAIL {exc}")
        result.error = f"synthesis failed: {exc}"
        result.catalysts = _safe_catalysts(findings, context, who, ticker)
        return result
    if debate_error:
        # Synthesis ran without the debate, so whatever confidence it claimed
        # rests on incomplete input. Say so rather than pass the stage's own
        # confidence through.
        thesis.confidence = "low"
        thesis.confidence_why = f"{debate_error}; thesis written without a structured debate"
    elif confidence and not thesis.confidence_why:
        thesis.confidence = confidence
        thesis.confidence_why = confidence_why
    if falsifiers and not thesis.falsifiers:
        thesis.falsifiers = falsifiers
    result.thesis = thesis

    # 6. Catalysts
    report("catalysts", "listing dated catalysts")
    result.catalysts = _safe_catalysts(findings, context, who, ticker, macro_block)

    result.llm_used = True
    result.models_used = list(dict.fromkeys(used)) or [verdict_model()]
    write_json(cache, result.model_dump())
    report("done", f"{len(findings)} findings · stance {thesis.stance}")
    return result



def _limits() -> dict:
    settings = env()
    return {
        "max_queries": settings.deepsearch_max_queries,
        "max_results": settings.deepsearch_max_results,
        "max_fetches": settings.deepsearch_max_fetches,
    }


def _safe_catalysts(findings: list[dict], context: str, who: str, ticker: str, macro_block: str = "") -> list:
    try:
        return _catalysts(findings, context, who, macro_block)
    except Exception as exc:
        log(f"deepdive {ticker}: catalysts FAIL {exc}")
        return []


def _catalysts(findings: list[dict], context: str, who: str, macro_block: str = "") -> list[Catalyst]:
    macro_part = (
        f"Macro / ISM backdrop (time-stamp catalysts against it where relevant):\n{macro_block}\n\n"
        if macro_block
        else ""
    )
    payload = chat_json(
        CATALYST_SYSTEM,
        f"Company: {who}\n\nFindings (numbered):\n{analysis.findings_block(findings)[:16000]}\n\n"
        f"SEC-filing context:\n{context[:2500]}\n\n"
        f"{macro_part}"
        'Write JSON: {"catalysts": [{"event": "...", "window": "...", "expected": "...", "finding_idx": 1}]}',
        model=verdict_model(),
    )
    out: list[Catalyst] = []
    for c in (payload.get("catalysts") or [])[:8]:
        event = str(c.get("event") or "").strip()
        if not event:
            continue
        src = {}
        try:
            i = int(c.get("finding_idx"))
            if 1 <= i <= len(findings):
                s = findings[i - 1].get("source") or {}
                if isinstance(s, dict):
                    src = {"title": s.get("title") or "", "url": s.get("url") or ""}
        except (TypeError, ValueError):
            pass
        out.append(
            Catalyst(
                event=event[:300],
                window=str(c.get("window") or "").strip()[:120],
                expected=str(c.get("expected") or "").strip()[:300],
                source=SourceRef(**src),
            )
        )
    return out