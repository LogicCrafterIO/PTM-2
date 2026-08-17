"""Assemble a qualitative research pack: EDGAR + Yahoo news + ISM snippet."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import yfinance as yf

from ptm.config import data_dir, toml_settings
from ptm.ingest.edgar import company_facts, filing_sections, latest_earnings_exhibit
from ptm.ingest.ism_sectors import gics_for_ism
from ptm.io import read_json, write_json
from ptm.log import log
from ptm.models import Candidate


def _yahoo_pack(ticker: str) -> dict:
    summary = ""
    ir = ""
    headlines: list[dict] = []
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        summary = str(info.get("longBusinessSummary") or "")[:1500]
        ir = str(info.get("irWebsite") or info.get("website") or "")
        news = []
        try:
            news = list(stock.news or [])
        except Exception:
            news = []
        for item in news[:10]:
            content = item.get("content") if isinstance(item.get("content"), dict) else item
            title = content.get("title") or item.get("title") or ""
            link = ""
            canonical = content.get("canonicalUrl") if isinstance(content, dict) else None
            if isinstance(canonical, dict):
                link = canonical.get("url") or ""
            link = link or item.get("link") or ""
            if title:
                headlines.append({"title": title, "link": link})
    except Exception:
        pass
    return {"summary": summary, "ir_website": ir, "headlines": headlines}


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


def _pack_text(payload: dict, limit: int) -> str:
    parts = [
        f"BUSINESS: {payload.get('summary') or ''}",
        f"IR: {payload.get('ir_website') or ''}",
        f"EDGAR FACTS: {json.dumps(payload.get('facts') or {}, default=str)}",
        f"ITEM 1 BUSINESS: {payload.get('business') or ''}",
        f"MD&A: {payload.get('mda') or ''}",
        f"8-K EX-99.1: {payload.get('earnings_exhibit') or ''}",
        "NEWS: " + " | ".join(h.get("title") or "" for h in payload.get("headlines") or []),
        f"ISM: {json.dumps(payload.get('ism') or {}, default=str)}",
    ]
    return "\n\n".join(parts)[:limit]


def research_pack(candidate: Candidate, force: bool = False) -> dict:
    ticker = candidate.ticker
    cache = data_dir("raw", "research", f"{ticker}.json")
    if cache.exists() and not force:
        cached = read_json(cache)
        if cached.get("text") and not cached.get("thin"):
            log(f"pack {ticker}: cache hit")
            return cached
    cfg = toml_settings()["llm"]
    limit = int(cfg.get("max_filing_chars") or 12000)
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
        sections = filing_sections(ticker, max_chars=min(4000, limit // 3))
    except Exception as exc:
        log(f"pack {ticker}: filings FAIL {exc}")
    try:
        log(f"pack {ticker}: 8-K exhibit")
        exhibit = latest_earnings_exhibit(ticker, max_chars=min(4000, limit // 3))
    except Exception as exc:
        log(f"pack {ticker}: exhibit FAIL {exc}")
    log(f"pack {ticker}: Yahoo summary/news")
    yahoo = _yahoo_pack(ticker)
    business = sections.get("business") or ""
    if len(business.strip()) < 40:
        business = yahoo.get("summary") or business
    payload = {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "facts": {k: v for k, v in facts.items() if k != "error"} if not facts.get("error") else {},
        "business": business,
        "mda": sections.get("mda") or "",
        "earnings_exhibit": exhibit,
        "summary": yahoo.get("summary") or "",
        "ir_website": yahoo.get("ir_website") or "",
        "headlines": yahoo.get("headlines") or [],
        "ism": _ism_snippet(candidate),
    }
    payload["text"] = _pack_text(payload, limit)
    payload["thin"] = len(payload["text"].strip()) < 400
    if not payload["thin"] or force:
        write_json(cache, payload)
    return payload
