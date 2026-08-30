"""Query planning and web research for the deep dive.

The planner decides WHAT to research; the searcher executes it; the extractor
turns raw pages into dated, sourced findings. Two LLM passes, one search loop.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from ptm.config import env
from ptm.deepsearch.models import DeepResearch, SearchFinding, SourceRef
from ptm.deepsearch.web import (
    available as web_available,
    log_usage,
    search_block,
    web_fetch,
    web_search,
)
from ptm.llm import JSON_HINT, chat_json, llm_available, verdict_model
from ptm.log import log

PLAN_SYSTEM = (
    "You are an equity research analyst planning a deep-dive investigation of ONE company. "
    "You will be given what the company's own SEC filings already say. Your job is to plan "
    "search queries that find what filings CANNOT: recent news, industry data, competitor "
    "moves, customer wins/losses, management changes, regulatory actions, analyst sentiment, "
    "and upcoming catalysts. "
    "Rules: 6-10 queries. Mix company-specific and industry-level queries. Include at least "
    "one query about the biggest RISK or bear argument, and at least one about COMPETITORS. "
    "Use time qualifiers like 'latest', 'this quarter', '2026' where useful. "
    + JSON_HINT
)

EXTRACT_SYSTEM = (
    "You are an equity research analyst extracting findings from web search results about ONE company. "
    "Extract every claim that bears on the company's fundamentals, industry, competition, or upcoming "
    "catalysts. Rules: every claim must carry its source index; every claim must state its date when the "
    "source shows one; prefer claims with numbers (revenue growth, margins, market share, order counts); "
    "skip marketing fluff and opinion pieces without evidence. " + JSON_HINT
)


def plan_queries(context: str, max_queries: int) -> list[str]:
    """LLM plans queries against a summary of what filings already say."""
    if not llm_available():
        return []
    payload = chat_json(
        PLAN_SYSTEM,
        f"Company context from SEC filings (may be truncated):\n{context[:6000]}\n\n"
        f"Write JSON: {{\"queries\": [\"...\"]}} with at most {max_queries} queries.",
    )
    queries = []
    for q in payload.get("queries") or []:
        text = str(q or "").strip()
        if 8 <= len(text) <= 200:
            queries.append(text)
    return queries[:max_queries]


def fallback_queries(ticker: str, name: str) -> list[str]:
    """No-LLM plan: generic but still covering the bear and competitor angles."""
    who = f"{name} {ticker}".strip()
    return [
        f"{who} latest earnings results",
        f"{who} revenue growth guidance",
        f"{who} competitors market share",
        f"{who} risks challenges problems",
        f"{who} industry trends outlook 2026",
        f"{who} analyst rating price target",
    ]


def _dedupe_urls(results: list[dict], limit: int) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for r in results:
        url = str(r.get("url") or "")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url or "")
    return (match.group(1) if match else "").lower()


# Domains worth the full-page fetch: earnings transcripts and filings carry the
# most change-dense text; random blog snippets do not.
FETCHABLE = (
    "sec.gov",
    "fool.com",
    "motleyfool.com",
    "seekingalpha.com",
    "investors.com",
    "businesswire.com",
    "prnewswire.com",
    "bloomberg.com",
    "reuters.com",
    "finance.yahoo.com",
    "cnbc.com",
    "benzinga.com",
    "investing.com",
)


def execute_search(queries: list[str], max_results: int, progress=None, use_cache: bool = True) -> tuple[list[dict], list[str]]:
    """Run every query, dedupe by URL, return (results, queries_actually_run)."""
    all_results: dict[str, dict] = {}
    ran: list[str] = []
    for i, q in enumerate(queries, 1):
        if progress is not None:
            try:
                progress("search", f"query {i}/{len(queries)}: {q}")
            except Exception:
                pass
        try:
            for r in web_search(q, max_results=max_results, use_cache=use_cache):
                url = r.get("url") or ""
                if url and url not in all_results:
                    all_results[url] = r
            ran.append(q)
        except Exception as exc:
            log(f"deepsearch: query FAILED {q!r}: {exc}")
    return list(all_results.values()), ran


def extract_findings(
    results: list[dict], ticker: str, name: str, chunk_size: int = 10, progress=None
) -> list[SearchFinding]:
    """LLM turns raw search-result snippets into dated, sourced findings.

    Chunked: one call over a few dozen results writes a JSON array long enough
    to hit the output limit, and a truncated array costs the whole research
    base. Per-chunk extraction caps each response; a chunk that still fails
    loses only its own slice.
    """
    if not results or not llm_available():
        return []
    findings: list[SearchFinding] = []
    chunks = list(range(0, len(results), chunk_size))
    for n, start in enumerate(chunks, 1):
        chunk = results[start : start + chunk_size]
        if progress is not None:
            try:
                progress("extract", f"summarising results {start + 1}-{min(start + chunk_size, len(results))} of {len(results)} (chunk {n}/{len(chunks)})")
            except Exception:
                pass
        try:
            findings.extend(_extract_chunk(chunk, ticker, name))
        except Exception as exc:
            log(f"deepsearch {ticker}: extraction chunk {start // chunk_size} FAILED: {exc}")
    return findings


def _extract_chunk(chunk: list[dict], ticker: str, name: str) -> list[SearchFinding]:
    block = search_block(chunk, per_result=900)
    who = f"{name} ({ticker})" if name else ticker
    payload = chat_json(
        EXTRACT_SYSTEM,
        f"Company: {who}\n\nWeb search results:\n{block[:20000]}\n\n"
        'Write JSON: {"findings": [{"claim": "...", "source_idx": 1, "category": '
        '"business|industry|competition|catalyst|sentiment", "dated": "2026-08-05 or empty"}]} '
        "with at most 8 findings, each claim under 240 characters.",
        model=verdict_model(),
    )
    findings: list[SearchFinding] = []
    for f in (payload.get("findings") or [])[:8]:
        claim = str(f.get("claim") or "").strip()
        if not claim:
            continue
        idx = f.get("source_idx")
        src = {}
        try:
            idx_int = int(idx)
            if 1 <= idx_int <= len(chunk):
                r = chunk[idx_int - 1]
                src = {"title": r.get("title") or "", "url": r.get("url") or ""}
        except (TypeError, ValueError):
            pass
        findings.append(
            SearchFinding(
                claim=claim[:400],
                source=SourceRef(**src),
                category=str(f.get("category") or "").strip().lower()[:24],
                dated=str(f.get("dated") or "").strip()[:32],
            )
        )
    return findings


def research(
    ticker: str,
    name: str,
    filing_context: str,
    max_queries: int,
    max_results: int,
    max_fetches: int,
    progress=None,
    use_cache: bool = True,
) -> DeepResearch:
    """Plan queries, run them, fetch key pages, extract findings.

    `progress(stage, detail)` reports sub-step state; every call is guarded so
    progress reporting can never break a dive. `use_cache=False` re-runs queries
    and fetches against the live API — a caller that forces a fresh dive must
    not silently reuse yesterday's search results.
    """
    research = DeepResearch(ticker=ticker)
    if not web_available():
        research.error = "no OLLAMA_API_KEY; web research skipped"
        return research
    if not llm_available():
        research.error = "no LLM key; query planning skipped"
        return research

    def report(stage: str, detail: str = "") -> None:
        if progress is not None:
            try:
                progress(stage, detail)
            except Exception:
                pass

    queries = plan_queries(filing_context, max_queries)
    if not queries:
        queries = fallback_queries(ticker, name)
        log(f"deepsearch {ticker}: using fallback queries")
    research.queries_run = queries

    results, ran = execute_search(queries, max_results, progress=report, use_cache=use_cache)
    research.search_used = bool(results)
    log_usage(f"{ticker} search", len(ran), 0)
    if not results:
        research.error = "web search returned no results"
        return research

    # Full-page fetch for the sources most likely to carry numbers in context.
    # Filter by domain BEFORE capping: capping first let the first four URLs
    # (all non-fetchable domains) consume the entire budget and fetched nothing.
    fetch_urls = [u for u in _dedupe_urls(results, len(results)) if _domain(u) in FETCHABLE][:max_fetches]
    pages: list[dict] = []
    if fetch_urls:
        report("fetch", f"fetching {len(fetch_urls)} full pages")
        with ThreadPoolExecutor(max_workers=4) as pool:
            for page in pool.map(lambda u: _safe_fetch(u, use_cache=use_cache), fetch_urls):
                if page.get("content"):
                    pages.append(page)
    log_usage(f"{ticker} fetch", 0, len(pages))
    research.fetched_pages = [
        SourceRef(title=p.get("title") or "", url=u) for p, u in zip(pages, fetch_urls) if p.get("content")
    ][:max_fetches]

    findings = extract_findings(results, ticker, name, progress=report)
    if pages:
        report("extract", f"reading {len(pages)} fetched pages")
        findings.extend(_extract_from_pages(pages, ticker, name))
    research.findings = findings
    research.sources = [f.source for f in findings if f.source.url]
    return research


def _safe_fetch(url: str, use_cache: bool = True) -> dict:
    try:
        return web_fetch(url, use_cache=use_cache)
    except Exception as exc:
        log(f"deepsearch: fetch FAILED {url}: {exc}")
        return {}


def _extract_from_pages(pages: list[dict], ticker: str, name: str, chunk_size: int = 2) -> list[SearchFinding]:
    """Second extraction pass over full-page text (transcripts, filings).

    Also chunked, by page: a single transcript can run tens of thousands of
    characters, and one oversized call was how the first PLTR run lost every
    page finding to truncation.
    """
    if not pages or not llm_available():
        return []
    who = f"{name} ({ticker})" if name else ticker
    out: list[SearchFinding] = []
    for start in range(0, len(pages), chunk_size):
        chunk = pages[start : start + chunk_size]
        try:
            payload = chat_json(
                EXTRACT_SYSTEM,
                f"Company: {who}\n\nFetched pages (full text):\n{fetch_pages_block(chunk)}\n\n"
                'Write JSON: {"findings": [{"claim": "...", "source_idx": 1, "category": '
                '"business|industry|competition|catalyst|sentiment", "dated": "..."}]} '
                "with at most 10 findings, each claim under 240 characters.",
                model=verdict_model(),
            )
        except Exception as exc:
            log(f"deepsearch {ticker}: page extraction chunk {start // chunk_size} FAILED: {exc}")
            continue
        for f in (payload.get("findings") or [])[:10]:
            claim = str(f.get("claim") or "").strip()
            if not claim:
                continue
            idx = f.get("source_idx")
            src = {}
            try:
                idx_int = int(idx)
                if 1 <= idx_int <= len(chunk):
                    src = {"title": chunk[idx_int - 1].get("title") or "", "url": chunk[idx_int - 1].get("url", "")}
            except (TypeError, ValueError):
                pass
            out.append(
                SearchFinding(
                    claim=claim[:400],
                    source=SourceRef(**src),
                    category=str(f.get("category") or "").strip().lower()[:24],
                    dated=str(f.get("dated") or "").strip()[:32],
                )
            )
    return out


def fetch_pages_block(pages: list[dict], per_page: int = 5000) -> str:
    lines = []
    for i, p in enumerate(pages, 1):
        lines.append(f"=== PAGE {i}: {p.get('title') or '(untitled)'} ===\n{(p.get('content') or '')[:per_page]}")
    return "\n\n".join(lines)