from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from concurrent.futures import ThreadPoolExecutor, as_completed

from ptm.asof import (
    AsOfUnavailable,
    as_of_date,
    coverage,
    day_slug,
    is_backdated,
    set_as_of,
    stamp,
    validate_as_of,
)
from ptm.fundamentals import build_fundamentals, source_warnings
from ptm.book import assemble_book
from ptm.books import assemble_books
from ptm.config import data_dir, env, ideas_dir, toml_settings
from ptm.gates import apply_process_gates, candidate_warnings, size_fraction
from ptm.ingest.company_research import research_pack
from ptm.ingest.edgar import company_facts
from ptm.ingest.expectations import expectations as market_expectations
from ptm.ingest.fred import fetch_fred_macro
from ptm.ingest.ism import scrape_ism
from ptm.ingest.ism_sectors import apply_ism_tilts, split_quota
from ptm.ingest.wikipedia import build_universe
from ptm.deepsearch.pipeline import run_deep_dive
from ptm.deepsearch.render import render_idea_markdown, render_markdown
from ptm.deepsearch.verdict import deepdive_extra, qual_from_deepdive
from ptm.ingest.yfinance_data import fetch_macro_prices, fetch_prices
from ptm.io import read_df, read_json, write_df, write_json
from ptm.earnings import resolve as resolve_earnings
from ptm.group_review import group_review, render_group_review
from ptm.llm import catalysts as llm_catalysts
from ptm.llm import fallback_template, llm_available, macro_narrative, qualitative, render_template
from ptm.log import log
from ptm.macro import build_dashboard
from ptm.revision_report import write_momentum
from ptm.themes import cohort_momentum
from ptm.themes import ism_alignment
from ptm.themes import ism_support as theme_ism_support
from ptm.themes import corroboration as theme_corroboration
from ptm.themes import record as record_themes
from ptm.organize import (
    group_by_bucket,
    group_by_sector,
    idea_paths,
    placements,
    sector_slug,
    write_index,
)
from ptm.models import Candidate, CatalystResult, IdeaState, MacroSnapshot, QualResult, Side, TimingResult, TradeIdea
from ptm.quant import build_candidates
from ptm.drift import consensus_drift
from ptm.ranking import cohort_rows, conviction, conviction_detail, momentum, reconcile_sides, ordered_candidates, write_ranking
from ptm.risk import earnings_in_window, prm_for



def apply_as_of(value: str | None, verify_ism: bool = True, allow_stale_ism: bool = False) -> None:
    """Validate and pin the run date.

    The calendar check says which ISM month the date is *entitled* to; the probe
    says whether ismworld.org still serves it. Old month URLs rotate to a
    navigation-only stub rather than 404ing, so only a parsed headline counts.
    Raises AsOfUnavailable when the run date cannot be honoured.
    """
    if not value:
        set_as_of(None)
        return
    day = validate_as_of(value)
    set_as_of(day)
    info = coverage()
    log(
        f"as-of: pinned to {info['as_of']} (real today {info['real_today']}); "
        f"ISM print {info['ism_report_month']}"
    )
    if not verify_ism or not is_backdated():
        return
    from ptm.ingest.ism import verify_ism_for

    log(f"as-of: probing ismworld.org for the {info['ism_report_month']} report")
    check = verify_ism_for(day)
    if check["ok"]:
        log(f"as-of: {check['target_month']} PMI {check['pmi']} confirmed live")
        return
    detail = "; ".join(check["errors"]) or "no headline parsed"
    if allow_stale_ism:
        fallback = check.get("fallback") or "none"
        log(f"as-of: {check['target_month']} unavailable ({detail}); continuing on {fallback} (--allow-stale-ism)")
        return
    fallback = check.get("fallback")
    hint = (
        f" The newest month that still parses is {fallback}; rerun with --allow-stale-ism "
        "to accept that older print, or pass --pmi-html/--services-html with reports you saved."
        if fallback
        else " No older month parses either; save the report and pass --pmi-html/--services-html."
    )
    set_as_of(None)
    raise AsOfUnavailable(
        f"as-of {day.isoformat()} needs the {check['target_month']} ISM report, but ismworld.org "
        f"no longer serves it ({detail})." + hint
    )


def _ensure_fundamentals(universe: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    """Fundamentals come from EDGAR for every run, live or backdated.

    Prices must already be on disk: market cap and both P/E ratios are struck
    against the run date's close.
    """
    return build_fundamentals(universe, force=force)


def _count_sides(sides: list[Side]) -> tuple[int, int]:
    longs = sum(1 for side in sides if side == Side.LONG)
    shorts = sum(1 for side in sides if side == Side.SHORT)
    return longs, shorts


def research_funnel(
    universe_n: int,
    fundamentals_n: int,
    candidates: list[Candidate],
    ideas: list[TradeIdea],
    book_ideas: list[TradeIdea],
) -> dict:
    cand_long, cand_short = _count_sides([c.side for c in candidates])
    idea_long, idea_short = _count_sides([i.candidate.side for i in ideas])
    book_long, book_short = _count_sides([i.candidate.side for i in book_ideas])
    warnings: list[str] = []
    if universe_n and fundamentals_n < 0.9 * universe_n:
        warnings.append(
            f"fundamentals cover {fundamentals_n}/{universe_n} tickers; PE screen is incomplete"
        )
    funnel = (
        f"universe {universe_n} → fundamentals {fundamentals_n} → "
        f"candidates {len(candidates)} ({cand_long}L/{cand_short}S) → "
        f"researched {len(ideas)} ({idea_long}L/{idea_short}S) → "
        f"book {len(book_ideas)} ({book_long}L/{book_short}S)"
    )
    return {
        "universe": int(universe_n),
        "fundamentals": int(fundamentals_n),
        "candidates": len(candidates),
        "candidates_long": cand_long,
        "candidates_short": cand_short,
        "ideas": len(ideas),
        "ideas_long": idea_long,
        "ideas_short": idea_short,
        "book": len(book_ideas),
        "book_long": book_long,
        "book_short": book_short,
        "funnel": funnel,
        "warnings": warnings,
    }


def ingest(
    max_tickers: int | None = None,
    force: bool = False,
    pmi_html: Path | str | None = None,
    services_html: Path | str | None = None,
    as_of: str | None = None,
) -> pd.DataFrame:
    if as_of:
        apply_as_of(as_of)
    uni_path = data_dir("curated", "universe.csv")
    log("ingest start")
    if force or not uni_path.exists():
        log("universe: building from Wikipedia")
        universe = build_universe()
    else:
        universe = read_df(uni_path)
        log(f"universe: cached {len(universe)} tickers")
    if max_tickers:
        universe = universe.head(max_tickers)
        log(f"universe: capped to {len(universe)} (--max-tickers {max_tickers})")
    fetch_macro_prices()
    try:
        scrape_ism(pmi_html=pmi_html, services_html=services_html)
    except Exception as exc:
        log(f"ism crashed: {exc}")
        write_json(data_dir("curated", "ism.json"), {"pmi": None, "nmi": None, "errors": [str(exc)]})
    try:
        fetch_fred_macro()
    except Exception as exc:
        log(f"fred crashed: {exc}")
        write_json(data_dir("curated", "macro_fred.json"), {"series": {}, "errors": [str(exc)]})
    # Prices first: fundamentals are priced off the run date's close.
    fetch_prices(universe["ticker"].tolist(), period="1y")
    _ensure_fundamentals(universe, force=force)
    log("ingest done")
    return universe


def screen() -> tuple[MacroSnapshot, list[Candidate]]:
    log("screen: building macro dashboard")
    snap = build_dashboard()
    universe = read_df(data_dir("curated", "universe.csv"))
    fundamentals = read_df(data_dir("curated", "yahoo_fundamentals.csv"))
    log(f"screen: universe {len(universe)} fundamentals {len(fundamentals)} bias={snap.bias.value}")
    candidates = apply_ism_tilts(build_candidates(universe, fundamentals), snap.sector_tilts)
    longs = sum(1 for c in candidates if c.side == Side.LONG)
    shorts = len(candidates) - longs
    log(f"screen: {len(candidates)} PE candidates ({longs}L/{shorts}S)")
    write_json(
        data_dir("curated", "candidates.json"),
        [c.model_dump() for c in candidates],
    )
    return snap, candidates


def _attach_evidence(candidate: Candidate) -> Candidate:
    try:
        facts = company_facts(candidate.ticker)
    except Exception:
        return candidate
    if facts.get("error"):
        return candidate
    ebit = facts.get("ebit")
    cash = facts.get("cash")
    debt = facts.get("debt")
    mcap = candidate.market_cap
    ev = None
    if mcap is not None:
        ev = mcap + (debt or 0) - (cash or 0)
    candidate.evidence = {
        "revenue": facts.get("revenue"),
        "net_income": facts.get("net_income"),
        "ebit": ebit,
        "cash": cash,
        "debt": debt,
        "ev": ev,
        "ev_ebit": (ev / ebit) if ev and ebit and ebit > 0 else None,
        "interest": facts.get("interest"),
    }
    return candidate



def _bound_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Drop any bar after the run date.

    ingest() already fetches a bounded window, but `ptm ideas --as-of` can be
    pointed at a prices.csv built by a live run, and that would be lookahead.
    """
    if prices is None or prices.empty or not is_backdated():
        return prices
    date_col = "date" if "date" in prices.columns else ("datetime" if "datetime" in prices.columns else None)
    if not date_col:
        return prices
    frame = prices.copy()
    frame["_d"] = pd.to_datetime(frame[date_col], errors="coerce", utc=True)
    cutoff = pd.Timestamp(as_of_date(), tz="UTC") + pd.Timedelta(hours=23, minutes=59)
    before = len(frame)
    frame = frame[frame["_d"].isna() | (frame["_d"] <= cutoff)].drop(columns=["_d"])
    if len(frame) < before:
        log(f"prices: dropped {before - len(frame)} bars after {as_of_date()} (backdated run)")
    return frame


def run_group_reviews(
    ideas: list[TradeIdea],
    snap: MacroSnapshot,
    day: str | None = None,
    skip_llm: bool = False,
) -> list:
    """Second LLM layer: read each sector group and each earnings-window group
    as a set, comparing their fundamental cases, and write the reviews next to
    the ideas. No price or technical input is used."""
    day = day or day_slug()
    if not ideas:
        return []
    by_ticker = {i.candidate.ticker: i for i in ideas}
    rows = placements(ideas)
    reviews = []

    sectors = group_by_sector(rows)
    buckets = group_by_bucket(rows)
    log(f"group review: {len(sectors)} sectors, {len(buckets)} earnings windows (llm={'off' if skip_llm else 'on'})")

    for sector, items in sectors.items():
        members = [by_ticker[r["ticker"]] for r in items if r["ticker"] in by_ticker]
        review = group_review(
            "sector", sector, members, macro_bias=snap.bias.value, as_of=day, skip_llm=skip_llm
        )
        reviews.append(review)
        path = ideas_dir(day, sector, "_SECTOR_REVIEW.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_group_review(review), encoding="utf-8")
        log(f"group review sector {sector}: {review.summary}")

    bucket_blocks = []
    for bucket, items in buckets.items():
        members = [by_ticker[r["ticker"]] for r in items if r["ticker"] in by_ticker]
        review = group_review(
            "earnings_window", bucket, members, macro_bias=snap.bias.value, as_of=day, skip_llm=skip_llm
        )
        reviews.append(review)
        bucket_blocks.append(render_group_review(review))
        log(f"group review window {bucket}: {review.summary}")

    write_json(data_dir("curated", "group_reviews.json"), [r.model_dump() for r in reviews])
    if bucket_blocks:
        combined = ideas_dir(day, "EARNINGS_REVIEW.md")
        header = [
            "# Cross-read by earnings window",
            "",
            f"As of: {day}",
            "",
            "Each section reads the fundamental cases of every idea reporting inside that",
            "window against each other. Windows are trading days from the run date.",
            "Sector-level reviews live in `<Sector>/_SECTOR_REVIEW.md`.",
            "",
            "---",
            "",
        ]
        body = "\n\n---\n\n".join(bucket_blocks)
        combined.write_text("\n".join(header) + body + "\n", encoding="utf-8")
        log(f"group review: wrote {combined.name}")
    return reviews


DEEPDIVE_MODE = "deepdive"
LEGACY_MODE = "legacy"


def resolve_qual_mode(qual_mode: str, skip_llm: bool) -> str:
    """Which qualitative engine this run will actually use.

    The deep dive is web-grounded: it needs an LLM and the Ollama web-search
    key, and its research is NOT point-in-time, so a backdated run silently
    serving today's news inside an "as of 2026-07-20" book would be lookahead.
    Backdated runs therefore fall back to the EDGAR-pack verdict, which draws
    only on what the run date can see. Falls are loud, once, at run start.
    """
    if str(qual_mode or DEEPDIVE_MODE).lower() not in {DEEPDIVE_MODE, LEGACY_MODE}:
        raise ValueError(f"unknown qual mode {qual_mode!r} (use 'deepdive' or 'legacy')")
    if str(qual_mode).lower() != DEEPDIVE_MODE:
        return LEGACY_MODE
    if skip_llm:
        return LEGACY_MODE
    if is_backdated():
        log(
            "ideas: BACKDATED run — web research is not point-in-time, so the deep-dive "
            "qualitative pass is unavailable; falling back to the EDGAR-pack verdict"
        )
        return LEGACY_MODE
    from ptm.deepsearch.web import available as web_available

    if not llm_available() or not web_available():
        log(
            "ideas: deep-dive qualitative unavailable (no LLM key / no OLLAMA_API_KEY for web "
            "search); falling back to the EDGAR-pack verdict"
        )
        return LEGACY_MODE
    return DEEPDIVE_MODE


def generate_ideas(
    max_candidates: int | None = None,
    skip_llm: bool = False,
    as_of: str | None = None,
    qual_mode: str = DEEPDIVE_MODE,
    dd_force: bool = False,
) -> list[TradeIdea]:
    if as_of:
        apply_as_of(as_of)
    qual_mode = resolve_qual_mode(qual_mode, skip_llm)
    snap, candidates = screen()
    if not skip_llm:
        try:
            log("ideas: macro LLM narrative")
            snap.llm_narrative = macro_narrative(snap)
            write_json(data_dir("curated", "macro_snapshot.json"), snap.model_dump())
        except Exception as exc:
            snap.notes.append(f"macro LLM failed: {exc}")
            log(f"ideas: macro LLM FAIL {exc}")
    prices = read_df(data_dir("curated", "prices.csv"))
    prices.columns = [str(c).lower() for c in prices.columns]
    market_hist = []
    yf_macro = data_dir("curated", "macro_yfinance.json")
    if yf_macro.exists():
        from ptm.io import read_json

        market_hist = [row["close"] for row in read_json(yf_macro).get("series", {}).get("spx", {}).get("history", [])]

    ranked_all = ordered_candidates(candidates)
    day = day_slug()
    if is_backdated():
        log(f"ideas: BACKDATED run, treating {day} as today")
    prices = _bound_prices(prices)
    write_ranking(candidates, day)
    if max_candidates is None:
        chosen = ranked_all
    else:
        chosen = split_quota(candidates, max_candidates)
    log(
        f"ideas: researching {len(chosen)} of {len(candidates)} PE candidates "
        f"(qual={qual_mode}, llm={'on' if not skip_llm and llm_available() else 'off'})"
    )
    fund = read_df(data_dir("curated", "yahoo_fundamentals.csv"))
    total = len(chosen)

    def _research_deep(idea: TradeIdea, cand: Candidate) -> str:
        """The deep dive IS the qualitative pass. Returns the rendered dive.

        Replaces the EDGAR research pack and the extract+verdict pair with a
        dossier: filings grounding, planned web research, drivers, a structured
        bull-vs-bear debate per driver and a synthesised stance. The adapter
        (ptm.deepsearch.verdict) maps that dossier onto the structured
        QualResult the gates and the book ranking consume, one verdict-model
        call whose quantified magnitudes are verified against the dive text.
        Results cache by ticker across runs; `dd_force` or an older
        `deepsearch_cache_days` cache reruns the dive.
        """
        report_rel = f"deepdive/{cand.ticker}/REPORT.md"
        cache_days = int(env().deepsearch_cache_days)
        try:
            result = run_deep_dive(
                cand.ticker,
                name=cand.name,
                sector=cand.sector,
                industry=cand.industry,
                force=dd_force,
                max_age_days=None if dd_force else cache_days,
            )
        except Exception as exc:
            idea.extra["deepdive"] = {"error": str(exc)[:200], "report": report_rel}
            raise
        deep_md = render_markdown(result)
        ideas_dir("deepdive", cand.ticker, "REPORT.md").write_text(deep_md, encoding="utf-8")
        idea.extra["deepdive"] = deepdive_extra(result, report_rel)
        log(
            f"idea {cand.ticker}: deep dive staged {'cached' if result.llm_used and not dd_force else 'run'} "
            f"stance={result.thesis.stance if result.thesis else 'none'} "
            f"findings={len(result.research.findings) if result.research else 0}"
        )
        idea.qual = qual_from_deepdive(result, cand, deep_md)
        return deep_md

    def _research(i: int, cand: Candidate) -> TradeIdea:
        log(f"idea {i}/{total} {cand.side.value} {cand.ticker}  ism={cand.ism_score} eg={cand.eg_case}")
        cand = _attach_evidence(cand)
        cand.warnings = candidate_warnings(cand)
        idea = TradeIdea(candidate=cand, state=IdeaState.IDENTIFIED)
        excerpt = json.dumps(cand.evidence, default=str)
        deep_md = ""
        pack = {}
        if qual_mode == DEEPDIVE_MODE:
            # The dive replaces pack + extract + verdict: its rendered report
            # becomes the evidence base the catalyst pass and the idea file read.
            try:
                log(f"idea {cand.ticker}: deep dive (filings + web research + debate)")
                deep_md = _research_deep(idea, cand)
                excerpt = deep_md
            except Exception as exc:
                log(f"idea {cand.ticker}: deep dive FAIL {exc}")
                idea.extra["deepdive_error"] = str(exc)
                idea.qual = None
        elif not skip_llm:
            try:
                log(f"idea {cand.ticker}: research pack (EDGAR)")
                pack = research_pack(cand)
                if pack.get("text"):
                    excerpt = pack["text"]
                log(f"idea {cand.ticker}: pack chars={len(excerpt)} thin={pack.get('thin')}")
            except Exception as exc:
                log(f"idea {cand.ticker}: research FAIL {exc}")
                idea.extra["research_error"] = str(exc)
        # Earnings date first: the expectations fetch needs it to choose the
        # option expiry that actually covers the print, and the verdict needs
        # the expectations. Nothing here depends on the qualitative result.
        idea.earnings = resolve_earnings(cand.ticker, None, ref=as_of_date())
        if idea.earnings.estimated:
            idea.extra["earnings_estimate"] = idea.earnings.basis
        expectations_payload = None
        if not skip_llm:
            try:
                log(f"idea {cand.ticker}: expectations")
                expectations_payload = market_expectations(cand.ticker, idea.earnings.date)
                if expectations_payload:
                    idea.extra["expectations"] = expectations_payload
                    idea.extra["expectations_summary"] = expectations_payload.get("summary") or []
            except Exception as exc:
                log(f"idea {cand.ticker}: expectations FAIL {exc}")
                idea.extra["expectations_error"] = str(exc)
        try:
            log(f"idea {cand.ticker}: qualitative")
            if qual_mode == DEEPDIVE_MODE:
                # The dive already ran; only apply the state transitions here
                # so a failed dive reads as "missing verdict", not as a pass.
                if idea.qual is None:
                    raise RuntimeError("deep dive produced no verdict")
            else:
                idea.qual = qualitative(
                    cand,
                    excerpt,
                    thin=bool(pack.get("thin")),
                    skip_llm=skip_llm,
                    expectations=expectations_payload,
                )
            if idea.qual.supports_outlier is True:
                idea.state = IdeaState.QUAL_PASS
            elif idea.qual.supports_outlier is False:
                idea.state = IdeaState.QUAL_FAIL
            else:
                idea.extra["qual"] = "insufficient_evidence" if not skip_llm else "llm_skipped"
            log(f"idea {cand.ticker}: qual supports_outlier={idea.qual.supports_outlier} state={idea.state.value}")
        except Exception as exc:
            log(f"idea {cand.ticker}: qualitative FAIL {exc}")
            idea.extra["qual_error"] = str(exc)
            idea.qual = None
        # The date itself was resolved above, from EDGAR filing cadence, so its
        # provenance survives. Reading the pre-projected date out of the
        # fundamentals table lost that: every idea came out labelled "published
        # earnings date" when EDGAR publishes no forward calendar at all and
        # every date is a projection.
        in_window, parsed = earnings_in_window(idea.earnings.date)
        try:
            log(f"idea {cand.ticker}: catalysts")
            idea.catalysts = llm_catalysts(cand, parsed, in_window, excerpt, skip_llm=skip_llm)
            if idea.state == IdeaState.QUAL_PASS:
                idea.state = IdeaState.CATALYST_PASS if idea.catalysts.tradeable else IdeaState.INVESTMENT_ONLY
            log(f"idea {cand.ticker}: catalysts tradeable={idea.catalysts.tradeable}")
        except Exception as exc:
            log(f"idea {cand.ticker}: catalysts FAIL {exc}")
            idea.extra["cat_error"] = str(exc)
        if idea.earnings.estimated:
            log(f"idea {cand.ticker}: {idea.earnings.basis}")
        idea.timing = TimingResult(comment="omitted: technical analysis is not part of this research process")
        idea.prm = prm_for(prices, cand, market_hist)
        idea.prm.size_fraction = size_fraction(idea)
        # Re-file any reason whose sign argues for the other side before anything
        # scores or gates on it, and record the correction on the idea so the
        # stored verdict matches the one the book was built from.
        if idea.qual is not None:
            for_items, against_items, contradictions = reconcile_sides(idea.qual, cand.side)
            if contradictions:
                idea.qual.evidence_for = for_items
                idea.qual.evidence_against = against_items
                idea.qual.red_flags = list(idea.qual.red_flags) + contradictions
                log(f"idea {cand.ticker}: {len(contradictions)} reason(s) re-filed as evidence against")
        blocks = apply_process_gates(idea)
        idea.extra["gates"] = blocks
        # Persist the conviction score and its arithmetic on the idea, so the
        # number that orders the book can be checked in the JSON rather than
        # recomputed from memory.
        idea.extra["conviction"] = conviction(idea)
        # The measured half of the expectation gap. Deterministic and recorded
        # on the idea so the ranking can be checked without an LLM call.
        idea.extra["drift"] = consensus_drift(idea.extra.get("expectations"))
        idea.extra["revision_momentum"] = momentum(idea)
        idea.extra["conviction_detail"] = conviction_detail(idea.qual, cand.side)
        log(f"idea {cand.ticker}: size={idea.prm.size_fraction} gates={blocks or 'none'}")
        qual = idea.qual or QualResult(supports_outlier=None, summary="missing qualitative", red_flags=["llm_skipped"] if skip_llm else [])
        cats = idea.catalysts or CatalystResult(earnings_date=parsed, earnings_in_window=in_window, tradeable=in_window, reason="missing catalysts")
        try:
            if qual_mode == DEEPDIVE_MODE:
                # The dive report IS the qualitative body; no template LLM call.
                idea.template_markdown = render_idea_markdown(
                    cand,
                    qual,
                    cats,
                    idea.earnings,
                    expectations_payload,
                    deep_md,
                    idea.extra.get("deepdive"),
                )
            else:
                idea.template_markdown = render_template(
                    cand,
                    qual,
                    cats,
                    idea.timing.comment if idea.timing else "",
                    skip_llm=skip_llm,
                    earnings=idea.earnings,
                    expectations=expectations_payload,
                )
            if idea.state in {IdeaState.CATALYST_PASS, IdeaState.QUAL_PASS}:
                idea.state = IdeaState.TEMPLATED
        except Exception as exc:
            idea.extra["template_error"] = str(exc)
        md = idea.template_markdown or ""
        if not md.strip() or md.lstrip().startswith("{") or md.lstrip().startswith("["):
            md = fallback_template(
                cand,
                qual,
                cats,
                idea.timing.comment if idea.timing else "",
                idea.earnings,
                expectations_payload,
            )
            idea.template_markdown = md
        md_path, json_path = idea_paths(idea, day=day)
        md_path.write_text(md, encoding="utf-8")
        write_json(json_path, idea.model_dump())
        log(f"idea {cand.ticker}: wrote {md_path.relative_to(ideas_dir(day))}")
        return idea

    # Each idea is independent until the group pass: its own EDGAR fetches, its
    # own web research, its own LLM calls, its own output files. All are
    # latency-bound, so a small pool cuts wall-clock sharply — and the deep
    # dive multiplies LLM calls per name, which makes the pool the difference
    # between hours and a lunch break. SEC stays inside its shared rate limit;
    # the pool size caps concurrent dives.
    workers = max(1, int((toml_settings().get("llm") or {}).get("idea_workers", 1)))
    if qual_mode == DEEPDIVE_MODE and workers > 1 and float((toml_settings().get("llm") or {}).get("max_rps") or 0) <= 0:
        log(
            f"ideas: {workers} workers deep-diving with no [llm].max_rps pacing — expect provider 429s "
            "on some calls (they retry); set max_rps to pace"
        )
    if workers > 1 and not skip_llm:
        log(f"ideas: {workers} workers")
        results: dict[int, TradeIdea] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_research, i, cand): i for i, cand in enumerate(chosen, start=1)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    log(f"idea #{index} crashed: {exc}")
        # Output order follows screen rank, not completion order.
        ideas: list[TradeIdea] = [results[i] for i in sorted(results)]
    else:
        ideas = [_research(i, cand) for i, cand in enumerate(chosen, start=1)]

    # Theme cohorts are cross-sectional, so they can only be formed once every
    # idea exists. A name's revision momentum is corroborated when the other
    # names exposed to the same theme are being revised the same way - the driver
    # is theme-wide rather than idiosyncratic. Filings and analyst estimates
    # only; nothing here reads a price, a return or a chart.
    cohorts = cohort_momentum(cohort_rows(ideas))
    # And the same theme vocabulary read against ISM: what purchasing managers
    # are raising, and whether those industries' new orders are growing. Two
    # independent populations answering different questions, so agreement is
    # corroboration rather than confirmation.
    ism_raw = read_json(data_dir("curated", "ism.json")) if data_dir("curated", "ism.json").exists() else {}
    ism_themes = ism_alignment(ism_raw if isinstance(ism_raw, dict) else {})
    for idea in ideas:
        themes = list((idea.qual.themes if idea.qual else None) or [])
        drift = idea.extra.get("drift") or {}
        idea.extra["theme_corroboration"] = theme_corroboration(
            themes, int(drift.get("direction") or 0), cohorts
        )
        idea.extra["ism_support"] = theme_ism_support(themes, ism_themes)
        idea.extra["revision_momentum"] = momentum(idea)
    write_json(data_dir("curated", "theme_ism_alignment.json"), ism_themes)
    write_json(data_dir("curated", "theme_cohorts.json"), cohorts)
    readable = sum(1 for c in cohorts.values() if c.get("available"))
    log(f"themes: {readable} of {len(cohorts)} cohorts large enough to read")

    # Second pass: a cross-sectional LLM read of each group's fundamental cases.
    reviews = run_group_reviews(ideas, snap, day=day, skip_llm=skip_llm)
    write_json(data_dir("curated", "ideas.json"), [i.model_dump() for i in ideas])

    rows = placements(ideas)
    notes = []
    if is_backdated():
        notes.append(f"Backdated run: every date below is measured from {day}, not from today.")
    index = write_index(rows, day=day, extra_notes=notes)
    log(f"index: {len(rows)} ideas mapped → {index.name}")

    book = assemble_book(ideas, snap.bias)
    log(f"book: {book.narrative}")
    # Written after the book so it can mark which names were actually taken.
    # This is the ranked answer to "which names look mispriced, by how much,
    # and why" - see ptm/mispricing.py.
    write_momentum(ideas, {i.candidate.ticker for i in book.ideas}, day=day)
    # And the same selection run separately per earnings window, so momentum is
    # held against a dated catalyst instead of averaged across horizons.
    assemble_books(ideas, snap.bias, day=day)
    record_themes(
        day,
        {
            i.candidate.ticker: [
                {"theme": str(t).rsplit(" (", 1)[0], "mentions": int(str(t).rsplit("(", 1)[1].rstrip(")"))}
                for t in (i.qual.themes or [])
                if "(" in str(t)
            ]
            for i in ideas
            if i.qual is not None and i.qual.themes
        },
    )
    return ideas


def run(
    max_tickers: int | None = None,
    max_candidates: int | None = None,
    skip_llm: bool = False,
    force: bool = False,
    pmi_html: Path | str | None = None,
    services_html: Path | str | None = None,
    as_of: str | None = None,
    qual_mode: str = DEEPDIVE_MODE,
    dd_force: bool = False,
) -> dict:
    if as_of:
        apply_as_of(as_of)
    running_mode = resolve_qual_mode(qual_mode, skip_llm)
    log(f"weekly run start (run date {as_of_date()}, qual={running_mode})")
    ingest(
        max_tickers=max_tickers,
        force=force,
        pmi_html=pmi_html,
        services_html=services_html,
    )
    ideas = generate_ideas(max_candidates=max_candidates, skip_llm=skip_llm, qual_mode=qual_mode, dd_force=dd_force)
    from ptm.eval import audit_run, write_audit
    from ptm.io import read_json

    snap = MacroSnapshot.model_validate(read_json(data_dir("curated", "macro_snapshot.json")))
    book = assemble_book(ideas, snap.bias)
    audit = audit_run()
    report = write_audit(audit)
    screened = read_df(data_dir("curated", "universe.csv"))
    fund_path = data_dir("curated", "yahoo_fundamentals.csv")
    fundamentals_n = int(len(read_df(fund_path))) if fund_path.exists() else 0
    cand_path = data_dir("curated", "candidates.json")
    candidates = [Candidate.model_validate(row) for row in read_json(cand_path)] if cand_path.exists() else []
    summary = research_funnel(len(screened), fundamentals_n, candidates, ideas, book.ideas)
    fund_frame = read_df(fund_path) if fund_path.exists() else pd.DataFrame()
    summary["warnings"] = list(summary["warnings"]) + source_warnings(fund_frame)
    if qual_mode == DEEPDIVE_MODE and running_mode != DEEPDIVE_MODE:
        summary["warnings"].append(
            "deep-dive qualitative unavailable for this run (llm/web key or backdated); used the EDGAR-pack verdict instead"
        )
    log(summary["funnel"])
    for warning in summary["warnings"]:
        log(f"WARNING {warning}")
    log(f"audit: {len(audit.findings)} findings → {report}")
    return {
        **summary,
        "bias": snap.bias.value,
        "llm": llm_available() and not skip_llm,
        "breaches": book.limit_breaches,
        "audit_findings": len(audit.findings),
        "audit_report": str(report),
        "as_of": coverage(),
    }
