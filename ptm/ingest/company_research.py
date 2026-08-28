"""Assemble a qualitative research pack: EDGAR filings + ISM snippet.

Filings only. Yahoo business summaries and news headlines were removed with
the rest of the vendor fundamentals — undated vendor text has no place in a
filings-based pack, and none of it survives a backdated run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ptm.asof import as_of_date, is_backdated
from ptm.config import data_dir, toml_settings
from ptm.ingest.edgar import company_facts, filing_sections, latest_earnings_exhibit
from ptm.ingest.ism_sectors import gics_for_ism
from ptm.ingest.transcripts import pack_section as transcript_section
from ptm.io import read_json, write_json
from ptm.log import log
from ptm.models import Candidate


def _ism_snippet(candidate: Candidate) -> dict:
    path = data_dir("curated", "ism.json")
    if not path.exists():
        return {}
    ism = read_json(path)
    hits: list[dict] = []
    orders_status = ""
    for report_key in ("manufacturing", "services"):
        report = ism.get(report_key) or {}
        for name in (report.get("new_orders_industries") or {}).get("contraction") or []:
            if gics_for_ism(name) == candidate.sector:
                orders_status = f"new orders contracting in {name}"
        for name in (report.get("new_orders_industries") or {}).get("growth") or []:
            if gics_for_ism(name) == candidate.sector and not orders_status:
                orders_status = f"new orders growing in {name}"
        for comment in report.get("comments") or []:
            if gics_for_ism(str(comment.get("industry") or "")) == candidate.sector:
                hits.append(comment)
    return {
        "ism_tilt": candidate.ism_tilt,
        "ism_why": candidate.ism_why,
        "new_orders": orders_status,
        "comments": hits[:3],
    }


def _reported_changes(candidate: Candidate) -> list[str]:
    """Period-over-period changes computed from figures already fetched.

    Filings state levels far more often than changes - "revenue was $87 million"
    rather than "revenue grew 9%" - and the verdict model does not reliably do
    the subtraction itself. These are the same numbers the screen runs on, stated
    as the changes they imply, so a claim can be sized without anyone guessing.
    """
    lines: list[str] = []
    eps0, eps1, eps2 = candidate.eps0, candidate.eps1, candidate.eps2
    # A percentage across a sign flip is meaningless: SLAB's -1.77 -> 2.93 reads
    # as "+218.7%", which would invite the model to size a claim on a number that
    # describes a loss turning into a profit, not growth. State the levels instead.
    flips = (eps0 is not None and eps1 is not None) and (eps0 <= 0 < eps1 or eps1 <= 0 < eps0)
    if candidate.eg1 is not None and not flips:
        basis = "consensus FY1 vs prior year" if eps1 is not None else "year 1"
        lines.append(f"EPS change, {basis}: {candidate.eg1 * 100:+.1f}%")
    elif flips:
        lines.append(
            f"EPS crosses zero ({eps0:.2f} -> {eps1:.2f}); a percentage change is not "
            "meaningful here, judge the swing in absolute terms"
        )
    if candidate.eg2 is not None and not (eps1 is not None and eps2 is not None and (eps1 <= 0 < eps2 or eps2 <= 0 < eps1)):
        lines.append(f"EPS change, year 2 vs year 1: {candidate.eg2 * 100:+.1f}%")
    if eps0 is not None and eps1 is not None:
        lines.append(f"EPS level: trailing {eps0:.2f} -> forward {eps1:.2f}")
    if eps2 is not None:
        lines.append(f"EPS level, year 2: {eps2:.2f}")
    if candidate.pe1 is not None and candidate.sector_pe1:
        lines.append(
            f"Forward P/E {candidate.pe1:.1f} against a sector median of "
            f"{candidate.sector_pe1:.1f} ({candidate.pe1 / candidate.sector_pe1:.1f}x)"
        )
    if candidate.pe1 is not None and candidate.industry_pe1:
        lines.append(
            f"Forward P/E {candidate.pe1:.1f} against an industry median of "
            f"{candidate.industry_pe1:.1f} ({candidate.pe1 / candidate.industry_pe1:.1f}x)"
        )
    try:
        from ptm.ingest.edgar import company_fundamentals

        facts = company_fundamentals(candidate.ticker, with_guidance=False)
        ttm, prior = facts.get("eps_ttm"), facts.get("eps_prior_ttm")
        if ttm is not None and prior not in (None, 0) and prior > 0:
            lines.append(
                f"Reported EPS change, trailing twelve months vs the year before: "
                f"{(ttm / prior - 1) * 100:+.1f}% ({prior:.2f} -> {ttm:.2f}, from filings)"
            )
    except Exception:
        pass
    return lines


def _pack_text(payload: dict, limit: int) -> str:
    parts = [
        f"BUSINESS: {payload.get('summary') or ''}",
        f"IR: {payload.get('ir_website') or ''}",
        f"EDGAR FACTS: {json.dumps(payload.get('facts') or {}, default=str)}",
        "REPORTED CHANGES (computed from filings and consensus; use these to size claims):\n"
        + "\n".join(f"  - {line}" for line in payload.get("reported_changes") or []),
        f"ITEM 1 BUSINESS: {payload.get('business') or ''}",
        f"MD&A: {payload.get('mda') or ''}",
        f"8-K EX-99.1: {payload.get('earnings_exhibit') or ''}",
        # Was assembled into the payload but never rendered into the text, so
        # enabling transcripts would silently have done nothing. Empty unless
        # [transcripts] is configured; see ptm/ingest/transcripts.py.
        f"EARNINGS CALL: {payload.get('transcript') or ''}",
        "NEWS: " + " | ".join(h.get("title") or "" for h in payload.get("headlines") or []),
        f"ISM: {json.dumps(payload.get('ism') or {}, default=str)}",
    ]
    return "\n\n".join(parts)[:limit]


def research_pack(candidate: Candidate, force: bool = False) -> dict:
    ticker = candidate.ticker
    suffix = f"_{as_of_date().isoformat()}" if is_backdated() else ""
    cache = data_dir("raw", "research", f"{ticker}{suffix}.json")
    if cache.exists() and not force:
        cached = read_json(cache)
        if cached.get("text") and not cached.get("thin"):
            log(f"pack {ticker}: cache hit")
            return cached
    cfg = toml_settings()["llm"]
    limit = int(cfg.get("max_filing_chars") or 12000)
    # Budget the pack by where the numbers actually are. Measured across 379
    # cached exhibits and 302 packs: the 8-K earnings release carries a median of
    # 22 quantitative expressions in its first 4k and 10 more in the next 4k,
    # while Item 1 Business has a median of 0 and MD&A 1. An equal three-way
    # split therefore spent a third of the budget on prose with no figures in it
    # and threw away the exhibit's second half.
    share_business = int(cfg.get("pack_business_chars") or 3000)
    share_mda = int(cfg.get("pack_mda_chars") or 3000)
    share_exhibit = int(cfg.get("pack_exhibit_chars") or 6000)
    facts = {}
    try:
        log(f"pack {ticker}: EDGAR facts")
        facts = company_facts(ticker)
    except Exception as exc:
        log(f"pack {ticker}: facts FAIL {exc}")
        facts = {}
    sections = {"business": "", "mda": ""}
    exhibit = ""
    try:
        log(f"pack {ticker}: 10-K/10-Q sections")
        sections = filing_sections(ticker, max_chars=max(share_business, share_mda))
    except Exception as exc:
        log(f"pack {ticker}: filings FAIL {exc}")
    try:
        log(f"pack {ticker}: 8-K exhibit")
        exhibit = latest_earnings_exhibit(ticker, max_chars=share_exhibit)
    except Exception as exc:
        log(f"pack {ticker}: exhibit FAIL {exc}")
    # No Yahoo business summary or news: undated vendor text has no place in a
    # filings-based pack, and none of it survives a backdated run anyway.
    business = (sections.get("business") or "")[:share_business]
    payload = {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "facts": {k: v for k, v in facts.items() if k != "error"} if not facts.get("error") else {},
        "business": business,
        "mda": (sections.get("mda") or "")[:share_mda],
        "earnings_exhibit": exhibit,
        "summary": "",
        "ir_website": "",
        "headlines": [],
        "transcript": transcript_section(ticker),
        "reported_changes": _reported_changes(candidate),
        "ism": _ism_snippet(candidate),
        "run_date": as_of_date().isoformat(),
        "backdated": is_backdated(),
        "withheld": "Yahoo summary/news not used: pack is EDGAR-only",
    }
    payload["text"] = _pack_text(payload, limit)
    payload["thin"] = len(payload["text"].strip()) < 400
    if not payload["thin"] or force:
        write_json(cache, payload)
    return payload
