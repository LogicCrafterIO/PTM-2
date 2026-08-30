"""Ollama web_search / web_fetch client.

Ollama Cloud exposes two non-OpenAI endpoints under the same API key:

    POST https://ollama.com/api/web_search   {"query", "max_results"}
    POST https://ollama.com/api/web_fetch    {"url"}

`web_search` results already carry a `content` extract, so a search alone is
often enough; `web_fetch` pulls the full page when a snippet needs the context
around a number. Both are called with the OLLAMA_API_KEY bearer token.
"""

from __future__ import annotations

import json
import threading

import requests

from ptm.config import data_dir, env
from ptm.io import write_json
from ptm.log import log

BASE = "https://ollama.com"
SEARCH_URL = f"{BASE}/api/web_search"
FETCH_URL = f"{BASE}/api/web_fetch"
TIMEOUT = 60

# The query/page caches are whole-file read-modify-write; parallel deep dives
# (the idea pipeline runs them under a thread pool) would otherwise interleave
# those reads and writes and lose entries.
_CACHE_LOCK = threading.Lock()


def _key() -> str:
    key = env().ollama_api_key
    if not key:
        raise RuntimeError("web search requires OLLAMA_API_KEY")
    return key


def _post(url: str, payload: dict) -> dict:
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def web_search(query: str, max_results: int = 8, use_cache: bool = True) -> list[dict]:
    """Search results as [{title, url, content}], cached per query."""
    cache = data_dir("raw", "deepsearch", "queries.json")
    key = f"{max_results}|{query.strip().lower()}"
    with _CACHE_LOCK:
        try:
            store = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        except Exception:
            store = {}
        if use_cache and key in store:
            return store[key]
    payload = _post(SEARCH_URL, {"query": query, "max_results": int(max_results)})
    results = [
        {
            "title": str(r.get("title") or ""),
            "url": str(r.get("url") or ""),
            "content": str(r.get("content") or ""),
        }
        for r in payload.get("results") or []
        if str(r.get("url") or "")
    ]
    with _CACHE_LOCK:
        try:
            store = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        except Exception:
            store = {}
        store[key] = results
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_json(cache, store)
    return results


def web_fetch(url: str, use_cache: bool = True) -> dict:
    """One page as {title, content}, cached per URL."""
    cache = data_dir("raw", "deepsearch", "pages.json")
    with _CACHE_LOCK:
        try:
            store = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        except Exception:
            store = {}
        if use_cache and url in store:
            return store[url]
    payload = _post(FETCH_URL, {"url": url})
    page = {
        "title": str(payload.get("title") or ""),
        "content": str(payload.get("content") or ""),
    }
    with _CACHE_LOCK:
        try:
            store = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        except Exception:
            store = {}
        store[url] = page
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_json(cache, store)
    return page


def available() -> bool:
    return bool(env().ollama_api_key)


def search_block(results: list[dict], per_result: int = 700) -> str:
    """Render results for a prompt, keeping the most change-dense part of each."""
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        content = (r.get("content") or "").strip()
        lines.append(f"[{i}] {r.get('title') or '(untitled)'}\n{r.get('url')}\n{content[:per_result]}")
    return "\n\n".join(lines)


def fetch_block(pages: list[dict], per_page: int = 4000) -> str:
    lines: list[str] = []
    for i, p in enumerate(pages, 1):
        content = (p.get("content") or "").strip()
        lines.append(f"=== PAGE {i}: {p.get('title') or '(untitled)'} ===\n{content[:per_page]}")
    return "\n\n".join(lines)


def log_usage(stage: str, queries: int, fetches: int) -> None:
    log(f"deepsearch {stage}: {queries} queries, {fetches} page fetches")