"""Bounded web search for the ranking — one budget per INDUSTRY, not per name.

The simple process searches per member: two queries for every ticker, spent
inside a per-ticker LLM call that no longer exists here. This process ranks a
whole industry in one pass, so the search budget is pooled the same way — two
industry-level queries that ask what is happening to the group into this
earnings season, then one query per member for name-specific developments
since its last filing. For a five-name industry that is 7 queries feeding one
prompt, against 10 feeding six prompts before.

Everything is snippets only: no page fetches, and every failure degrades to
running without search rather than killing the pass. The snippets carry no
verified dates, so the prompt frames them as leads — the ranking's dated facts
come from the deterministic packet (ptm_setups.inputs), never from here.
"""

from __future__ import annotations

from datetime import date

from ptm.log import log

# Per-industry ceiling on queries. Two industry-level plus one per member, so a
# group larger than ten names starts dropping the tail of the member queries —
# logged when it happens, never silently.
MAX_QUERIES_PER_GROUP = 12
RESULTS_PER_QUERY = 5
SNIPPET_CHARS = 240


def _queries(theme: str, members: list[dict], ref: date) -> list[str]:
    """The industry queries first, then one per member — truncated to the cap."""
    group = str(theme or "").strip()
    out = [
        f"{group} industry earnings season {ref.year} guidance outlook",
        f"{group} companies estimate revisions next quarter demand",
        # the forward-looking demand question: orders, backlogs, surveys — the
        # raw material for the group's why-not-COLD judgement, which has to be
        # about what happens next, not a restatement of the revision table
        f"{group} industry new orders backlog demand outlook next quarter",
    ] if group else []
    for m in members:
        name = str(m.get("name") or "").strip()
        ticker = str(m.get("ticker") or "").strip()
        who = f"{name} {ticker}".strip() if name else ticker
        if who:
            out.append(f"{who} guidance outlook latest quarter earnings")
    return out[:MAX_QUERIES_PER_GROUP]


def group_snippets(theme: str, members: list[dict], ref: date) -> dict | None:
    """{searches: [{query, title, snippet}], queries: n} for one industry, or None.

    Returns None when there is no search key at all — the ranking then runs on
    the filed pack and the consensus data alone and says so.
    """
    try:
        from ptm.deepsearch.web import available, web_search
    except Exception:
        return None
    if not available():
        return None
    queries = _queries(theme, members, ref)
    if not queries:
        return None
    wanted = 2 + len(members)
    if wanted > MAX_QUERIES_PER_GROUP:
        log(f"setups search {theme}: {wanted} queries wanted, capped at {MAX_QUERIES_PER_GROUP} "
            f"— {wanted - MAX_QUERIES_PER_GROUP} member query(ies) dropped")
    searches: list[dict] = []
    seen: set[str] = set()
    ran = 0
    for query in queries:
        try:
            results = web_search(query, max_results=RESULTS_PER_QUERY)
        except Exception as exc:
            log(f"setups search {theme}: '{query[:40]}' failed ({str(exc)[:60]}) — continuing without it")
            continue
        ran += 1
        for r in results[:RESULTS_PER_QUERY]:
            title = (r.get("title") or "").strip()
            snippet = (r.get("content") or "").strip()[:SNIPPET_CHARS]
            key = (r.get("url") or title or snippet)[:200]
            if not (title or snippet) or key in seen:
                continue
            seen.add(key)
            searches.append({"query": query, "title": title, "snippet": snippet})
    if not searches:
        return None
    log(f"setups search {theme}: {ran} query(ies), {len(searches)} snippet(s)")
    return {"searches": searches, "queries": ran}
