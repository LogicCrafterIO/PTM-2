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
from ptm.config import data_dir, ideas_dir, toml_settings
from ptm.gates import apply_process_gates, candidate_warnings, size_fraction
from ptm.ingest.company_research import research_pack
from ptm.ingest.edgar import company_facts
from ptm.ingest.fred import fetch_fred_macro
from ptm.ingest.ism import scrape_ism
from ptm.ingest.ism_sectors import apply_ism_tilts, split_quota
from ptm.ingest.wikipedia import build_universe
from ptm.ingest.yfinance_data import fetch_macro_prices, fetch_prices
from ptm.io import read_df, write_df, write_json
from ptm.earnings import resolve as resolve_earnings
from ptm.group_review import group_review, render_group_review
from ptm.llm import catalysts as llm_catalysts
from ptm.llm import fallback_template, llm_available, macro_narrative, qualitative, render_template
from ptm.log import log
from ptm.macro import build_dashboard
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
from ptm.ranking import conviction, conviction_detail, ordered_candidates, write_ranking
from ptm.timing_prm import earnings_in_window, prm_for



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


def generate_ideas(
    max_candidates: int | None = None,
    skip_llm: bool = False,
    as_of: str | None = None,
) -> list[TradeIdea]:
    if as_of:
        apply_as_of(as_of)
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
        f"(llm={'on' if not skip_llm and llm_available() else 'off'})"
    )
    fund = read_df(data_dir("curated", "yahoo_fundamentals.csv"))
    total = len(chosen)

    def _research(i: int, cand: Candidate) -> TradeIdea:
        log(f"idea {i}/{total} {cand.side.value} {cand.ticker}  ism={cand.ism_score} eg={cand.eg_case}")
        cand = _attach_evidence(cand)
        cand.warnings = candidate_warnings(cand)
        idea = TradeIdea(candidate=cand, state=IdeaState.IDENTIFIED)
        excerpt = json.dumps(cand.evidence, default=str)
        pack = {}
        if not skip_llm:
            try:
                log(f"idea {cand.ticker}: research pack (EDGAR)")
                pack = research_pack(cand)
                if pack.get("text"):
                    excerpt = pack["text"]
                log(f"idea {cand.ticker}: pack chars={len(excerpt)} thin={pack.get('thin')}")
            except Exception as exc:
                log(f"idea {cand.ticker}: research FAIL {exc}")
                idea.extra["research_error"] = str(exc)
        try:
            log(f"idea {cand.ticker}: qualitative")
            idea.qual = qualitative(cand, excerpt, thin=bool(pack.get("thin")), skip_llm=skip_llm)
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
        # Resolve the earnings date FIRST, and from EDGAR filing cadence, so its
        # provenance survives. Reading the pre-projected date out of the
        # fundamentals table lost that: every idea came out labelled "published
        # earnings date" when EDGAR publishes no forward calendar at all and
        # every date is a projection.
        idea.earnings = resolve_earnings(cand.ticker, None, ref=as_of_date())
        if idea.earnings.estimated:
            idea.extra["earnings_estimate"] = idea.earnings.basis
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
        blocks = apply_process_gates(idea)
        idea.extra["gates"] = blocks
        # Persist the conviction score and its arithmetic on the idea, so the
        # number that orders the book can be checked in the JSON rather than
        # recomputed from memory.
        idea.extra["conviction"] = conviction(idea)
        idea.extra["conviction_detail"] = conviction_detail(idea.qual)
        log(f"idea {cand.ticker}: size={idea.prm.size_fraction} gates={blocks or 'none'}")
        qual = idea.qual or QualResult(supports_outlier=None, summary="missing qualitative", red_flags=["llm_skipped"] if skip_llm else [])
        cats = idea.catalysts or CatalystResult(earnings_date=parsed, earnings_in_window=in_window, tradeable=in_window, reason="missing catalysts")
        try:
            idea.template_markdown = render_template(
                cand,
                qual,
                cats,
                idea.timing.comment if idea.timing else "",
                idea.prm.model_dump() if idea.prm else {},
                skip_llm=skip_llm,
                earnings=idea.earnings,
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
                idea.prm.model_dump() if idea.prm else {},
                idea.earnings,
            )
            idea.template_markdown = md
        md_path, json_path = idea_paths(idea, day=day)
        md_path.write_text(md, encoding="utf-8")
        write_json(json_path, idea.model_dump())
        log(f"idea {cand.ticker}: wrote {md_path.relative_to(ideas_dir(day))}")
        return idea

    # Each idea is independent until the group pass: its own EDGAR fetches, its
    # own LLM calls, its own output files. Both are latency-bound, so a small
    # pool cuts wall-clock sharply. SEC stays inside its shared rate limit; the
    # pool size caps concurrent LLM calls.
    workers = max(1, int((toml_settings().get("llm") or {}).get("idea_workers", 1)))
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
    return ideas


def run(
    max_tickers: int | None = None,
    max_candidates: int | None = None,
    skip_llm: bool = False,
    force: bool = False,
    pmi_html: Path | str | None = None,
    services_html: Path | str | None = None,
    as_of: str | None = None,
) -> dict:
    if as_of:
        apply_as_of(as_of)
    log(f"weekly run start (run date {as_of_date()})")
    ingest(
        max_tickers=max_tickers,
        force=force,
        pmi_html=pmi_html,
        services_html=services_html,
    )
    ideas = generate_ideas(max_candidates=max_candidates, skip_llm=skip_llm)
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
