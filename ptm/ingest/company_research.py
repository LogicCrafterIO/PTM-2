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
    suffix = f"_{as_of_date().isoformat()}" if is_backdated() else ""
    cache = data_dir("raw", "research", f"{ticker}{suffix}.json")
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
    # No Yahoo business summary or news: undated vendor text has no place in a
    # filings-based pack, and none of it survives a backdated run anyway.
    business = sections.get("business") or ""
    payload = {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "facts": {k: v for k, v in facts.items() if k != "error"} if not facts.get("error") else {},
        "business": business,
        "mda": sections.get("mda") or "",
        "earnings_exhibit": exhibit,
        "summary": "",
        "ir_website": "",
        "headlines": [],
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
