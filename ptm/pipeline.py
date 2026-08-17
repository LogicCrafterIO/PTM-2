from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ptm.book import assemble_book
from ptm.config import data_dir, ideas_dir
from ptm.gates import apply_process_gates, candidate_warnings, size_fraction
from ptm.ingest.company_research import research_pack
from ptm.ingest.edgar import company_facts
from ptm.ingest.fred import fetch_fred_macro
from ptm.ingest.ism import scrape_ism
from ptm.ingest.ism_sectors import apply_ism_tilts, split_quota
from ptm.ingest.wikipedia import build_universe
from ptm.ingest.yfinance_data import fetch_fundamentals, fetch_macro_prices, fetch_prices
from ptm.io import read_df, write_df, write_json
from ptm.llm import catalysts as llm_catalysts
from ptm.llm import fallback_template, llm_available, macro_narrative, qualitative, render_template
from ptm.log import log
from ptm.macro import build_dashboard
from ptm.models import Candidate, CatalystResult, IdeaState, MacroSnapshot, QualResult, Side, TimingResult, TradeIdea
from ptm.quant import build_candidates
from ptm.ranking import ordered_candidates, write_ranking
from ptm.timing_prm import earnings_in_window, prm_for


def _ensure_fundamentals(universe: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    fund_path = data_dir("curated", "yahoo_fundamentals.csv")
    tickers = [str(t) for t in universe["ticker"].tolist() if t]
    cached = read_df(fund_path) if fund_path.exists() else pd.DataFrame()
    have = set()
    if not cached.empty and "ticker" in cached.columns:
        have = set(cached["ticker"].astype(str))
    if force:
        log(f"fundamentals: --force refetch of {len(tickers)} tickers")
        return fetch_fundamentals(tickers)
    missing = [t for t in tickers if t not in have]
    log(f"fundamentals cache {len(have)} / universe {len(tickers)}; missing {len(missing)}")
    if not missing:
        return cached
    log(f"fundamentals: backfilling {len(missing)} tickers starting at {missing[0]}")
    fresh = fetch_fundamentals(missing, persist=False)
    combined = pd.concat([cached, fresh], ignore_index=True) if not cached.empty else fresh
    if combined.empty:
        return combined
    combined = combined.drop_duplicates(subset=["ticker"], keep="last")
    write_df(fund_path, combined)
    return combined


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
) -> pd.DataFrame:
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
    _ensure_fundamentals(universe, force=force)
    fetch_prices(universe["ticker"].tolist(), period="1y")
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


def generate_ideas(max_candidates: int | None = None, skip_llm: bool = False) -> list[TradeIdea]:
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
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_ranking(candidates, day)
    if max_candidates is None:
        chosen = ranked_all
    else:
        chosen = split_quota(candidates, max_candidates)
    log(
        f"ideas: researching {len(chosen)} of {len(candidates)} PE candidates "
        f"(llm={'on' if not skip_llm and llm_available() else 'off'})"
    )
    ideas: list[TradeIdea] = []
    fund = read_df(data_dir("curated", "yahoo_fundamentals.csv"))
    earnings_map = {row["ticker"]: row.get("earnings_date") for _, row in fund.iterrows()}

    for i, cand in enumerate(chosen, start=1):
        log(f"idea {i}/{len(chosen)} {cand.side.value} {cand.ticker}  ism={cand.ism_score} eg={cand.eg_case}")
        cand = _attach_evidence(cand)
        cand.warnings = candidate_warnings(cand)
        idea = TradeIdea(candidate=cand, state=IdeaState.IDENTIFIED)
        excerpt = json.dumps(cand.evidence, default=str)
        pack = {}
        if not skip_llm:
            try:
                log(f"idea {cand.ticker}: research pack (EDGAR + Yahoo)")
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
        in_window, parsed = earnings_in_window(earnings_map.get(cand.ticker))
        try:
            log(f"idea {cand.ticker}: catalysts")
            idea.catalysts = llm_catalysts(cand, parsed, in_window, excerpt, skip_llm=skip_llm)
            if idea.state == IdeaState.QUAL_PASS:
                idea.state = IdeaState.CATALYST_PASS if idea.catalysts.tradeable else IdeaState.INVESTMENT_ONLY
            log(f"idea {cand.ticker}: catalysts tradeable={idea.catalysts.tradeable}")
        except Exception as exc:
            log(f"idea {cand.ticker}: catalysts FAIL {exc}")
            idea.extra["cat_error"] = str(exc)
        idea.timing = TimingResult(comment="omitted: technical analysis is not part of this research process")
        idea.prm = prm_for(prices, cand, market_hist)
        idea.prm.size_fraction = size_fraction(idea)
        blocks = apply_process_gates(idea)
        idea.extra["gates"] = blocks
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
            )
            idea.template_markdown = md
        ideas.append(idea)
        path = ideas_dir(day, f"{cand.side.value}_{cand.ticker}.md")
        path.write_text(md, encoding="utf-8")
        write_json(path.with_suffix(".json"), idea.model_dump())
        log(f"idea {cand.ticker}: wrote {path.name}")
    write_json(data_dir("curated", "ideas.json"), [i.model_dump() for i in ideas])
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
) -> dict:
    log("weekly run start")
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
    }
