"""Earnings call transcripts.

Why this exists: the 8-K earnings release states levels far more often than
changes. Measured across 379 releases, the median carries 2 change-phrases
("revenue grew 9%", "margins up 200bps") against 9 level-phrases ("revenue was
$87 million"), and 37% carry no change-phrase at all. That is the ceiling on how
often the qualitative verdict can size a claim, and no amount of prompting moves
it. Call transcripts are the opposite: prepared remarks are dominated by
period-over-period language, and the Q&A surfaces the risks that make good
evidence against a trade.

Transcripts are NOT in EDGAR. Companies file the release, not the call - checked
across 379 cached exhibits, 4% carry any transcript marker, and those are stray
attachments. Nor are they reliably scrapeable: Motley Fool returns 429 on a first
request, Investing.com 403, and Seeking Alpha serves them but its terms prohibit
scraping and the content is paywalled. A scraper built against those would break
immediately or breach terms, so this module talks to APIs that license the
content instead.

It is disabled until a key is configured, and does nothing silently in the
meantime. See docs/FEATURE-LIMITATIONS.md.
"""

from __future__ import annotations

import os
import re
import time
from datetime import date

import requests

from ptm.asof import as_of_date, is_backdated
from ptm.config import data_dir, toml_settings
from ptm.io import read_json, write_json
from ptm.log import log

# Period-over-period language: the thing releases lack and calls are full of.
CHANGE_RE = re.compile(
    r"\b(grew|increased|decreased|declined|up|down|rose|fell|expanded|improved|accelerat\w+)\b"
    r"[^.]{0,40}?\d+(?:\.\d+)?\s*(?:%|percent|basis points|bps)",
    re.I,
)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent|million|billion|bps)", re.I)


def _cfg() -> dict:
    return toml_settings().get("transcripts") or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False)) and bool(api_key())


def api_key() -> str:
    """Key from the environment. Never committed, never logged."""
    return (os.environ.get(str(_cfg().get("api_key_env") or "TRANSCRIPT_API_KEY")) or "").strip()


def provider() -> str:
    return str(_cfg().get("provider") or "fmp").strip().lower()


def _max_chars() -> int:
    return int(_cfg().get("max_chars") or 6000)


def _quarters() -> int:
    return int(_cfg().get("quarters") or 2)


# --- providers ---------------------------------------------------------------
# Each returns a list of {date, quarter, year, text}, newest first. Add a
# provider by writing one function and registering it below; nothing else in the
# pipeline needs to change.


def _fmp(ticker: str, key: str, limit: int) -> list[dict]:
    """Financial Modeling Prep. Returns dated transcripts by quarter."""
    url = f"https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}"
    response = requests.get(url, params={"apikey": key, "limit": limit}, timeout=45)
    if response.status_code >= 400:
        return []
    out = []
    for row in response.json() or []:
        out.append(
            {
                "date": str(row.get("date") or "")[:10],
                "quarter": row.get("quarter"),
                "year": row.get("year"),
                "text": str(row.get("content") or ""),
            }
        )
    return out


def _finnhub(ticker: str, key: str, limit: int) -> list[dict]:
    """Finnhub. Two calls: list the transcript ids, then fetch each."""
    index = requests.get(
        "https://finnhub.io/api/v1/stock/transcripts/list",
        params={"symbol": ticker, "token": key},
        timeout=45,
    )
    if index.status_code >= 400:
        return []
    out = []
    for row in (index.json() or {}).get("transcripts", [])[:limit]:
        detail = requests.get(
            "https://finnhub.io/api/v1/stock/transcripts",
            params={"id": row.get("id"), "token": key},
            timeout=45,
        )
        if detail.status_code >= 400:
            continue
        payload = detail.json() or {}
        speech = " ".join(
            str(seg.get("speech") or "") if isinstance(seg.get("speech"), str)
            else " ".join(seg.get("speech") or [])
            for seg in payload.get("transcript") or []
        )
        out.append(
            {
                "date": str(payload.get("time") or row.get("time") or "")[:10],
                "quarter": payload.get("quarter") or row.get("quarter"),
                "year": payload.get("year") or row.get("year"),
                "text": speech,
            }
        )
        time.sleep(0.3)
    return out


PROVIDERS = {"fmp": _fmp, "finnhub": _finnhub}


# --- selection ---------------------------------------------------------------


def densest_window(text: str, size: int) -> str:
    """The passage carrying the most period-over-period language.

    A transcript runs to tens of thousands of characters and the prepared
    remarks - where the numbers live - are not always at the top. Taking the
    head would often capture the operator's preamble and the safe-harbour
    statement, so score windows and keep the best one.
    """
    text = " ".join((text or "").split())
    if len(text) <= size:
        return text
    best, best_score = text[:size], -1
    # The stride must stay well inside the window or passages fall between
    # samples entirely - a 500-char floor made a 300-char window skip content.
    step = max(1, size // 6)
    for start in range(0, len(text) - size + 1, step):
        window = text[start : start + size]
        score = len(CHANGE_RE.findall(window)) * 3 + len(NUMBER_RE.findall(window))
        if score > best_score:
            best, best_score = window, score
    return best


def _cache_path(ticker: str):
    suffix = f"_{as_of_date().isoformat()}" if is_backdated() else ""
    return data_dir("raw", "transcripts", f"{ticker}{suffix}.json")


def fetch(ticker: str) -> list[dict]:
    """Transcripts for one ticker, newest first, bounded by the run date.

    A backdated run keeps only calls that had already happened, the same rule
    applied to filings and prices. Returns [] when disabled or unavailable -
    the pack simply carries on without it.
    """
    if not enabled():
        return []
    cache = _cache_path(ticker)
    if cache.exists():
        try:
            cached = read_json(cache)
            if isinstance(cached, list):
                return cached
        except Exception:
            pass
    fetcher = PROVIDERS.get(provider())
    if fetcher is None:
        log(f"transcripts: unknown provider {provider()!r}; expected one of {sorted(PROVIDERS)}")
        return []
    try:
        rows = fetcher(ticker, api_key(), _quarters())
    except Exception as exc:
        log(f"transcripts {ticker}: FAIL {exc}")
        return []

    cutoff = as_of_date().isoformat()
    kept = []
    for row in rows:
        if not row.get("text"):
            continue
        # An undated transcript cannot be shown to be in the past, so a
        # backdated run refuses it rather than risk lookahead.
        if is_backdated() and (not row.get("date") or row["date"] > cutoff):
            continue
        kept.append(
            {
                "date": row.get("date"),
                "quarter": row.get("quarter"),
                "year": row.get("year"),
                "text": densest_window(row["text"], _max_chars()),
                "change_phrases": len(CHANGE_RE.findall(row["text"])),
            }
        )
    kept = kept[: _quarters()]
    write_json(cache, kept)
    return kept


def pack_section(ticker: str) -> str:
    """The transcript block for the research pack, or an empty string."""
    rows = fetch(ticker)
    if not rows:
        return ""
    parts = []
    for row in rows:
        label = f"Q{row.get('quarter')} {row.get('year')}" if row.get("quarter") else "call"
        parts.append(f"[{label}, {row.get('date') or 'undated'}] {row['text']}")
    return "\n\n".join(parts)


def coverage_note(with_transcript: int, total: int) -> list[str]:
    """Honest caveat for the run summary."""
    if not _cfg().get("enabled", False):
        return []
    if not api_key():
        return [
            "Transcripts enabled but no API key found; the research pack is filings-only "
            "and evidence will rarely be quantified (releases state levels, not changes)."
        ]
    if total and with_transcript < 0.5 * total:
        return [
            f"Call transcripts covered only {with_transcript}/{total} names; the rest fall back "
            "to the earnings release, where period-over-period figures are scarcer."
        ]
    return []
