"""The print-focused qual: what the NEXT earnings trade needs — no deep dive.

The deep dive is a backward-looking research artifact that can lag the calendar
(its "upcoming quarter" references go stale the day a print lands), so the
flag-justification review cannot lean on it. This module builds the separate,
print-focused qual from inputs that are fresh by construction:

1. the EDGAR research pack (data/raw/research/<ticker>.json) — the LAST FILED
   quarter's actuals: the 8-K earnings exhibit, MD&A language, pre-computed
   consensus changes. Sourced text, no LLM and no dive in the chain;
2. two bounded Ollama web searches per member (the same client the dive engine
   uses) — developments since the pack was filed: guidance updates, news, the
   upcoming-print preview chatter. Snippets only, no page fetches, and the
   prompt treats them as context with unverified recency, never as dated facts;
3. the expectations cache — the name's own 90d estimate direction, analyst
   up/down counts, the print date;
4. the consensus table — FY1/FY2 EPS, EG1/EG2, PE1/PEG1, the theme-relative
   valuation flag (quant.py);
5. the theme context — thesis, lean/breadth, bellwether, peer prints.

One small LLM call per member distils that into a next-print brief: what the
upcoming print will REVEAL (the quarter it reports is computed, not guessed),
which KPIs decide the trade, and how the following quarter(s) set up. The
group review reads these briefs — never the dive — when judging whether a
valuation flag is justified.
"""
from __future__ import annotations

import json
from datetime import date

from ptm.llm import JSON_HINT, chat_json, llm_available
from ptm.log import log
from ptm_simple import simple_dir

_SYSTEM = (
    "You write the NEXT-PRINT brief for one equity idea in a theme process. The trade is built around "
    "the next earnings print and the 2-4 months around it. You are given: today's date; the print date and "
    "the fiscal quarter it REPORTS (computed for you — trust it); the name's own 90d estimate direction and "
    "analyst revision counts; consensus FY1/FY2 EPS and growth; the theme-relative valuation flag with its "
    "ratios; the theme's state, thesis and peer prints; the research pack's latest-filed facts (EDGAR "
    "only: the last earnings exhibit's actuals, MD&A forward language, reported consensus changes); and "
    "web-search snippets of developments since those filings. Write 4-7 FORWARD-LOOKING points on what "
    "this next print will REVEAL and how the following quarter(s) set up for the trade side given in the "
    "packet (a side-neutral candidate gets what would CREATE a side) — this is the material a "
    "next-earnings trade is decided on. Rules: use the given numbers as the base and never invent one; "
    "quarters that already ended are FACTS, never open questions; the brief must not hedge about any "
    "period that ended before today; no price targets, no technicals, no price action; one or two short "
    "sentences per point, plain language. The web snippets carry no verified dates — treat them as leads "
    "and context: anything they describe as upcoming may already have happened, so lean on the dated "
    "context lines and say 'reports suggest' when a fact comes only from a snippet. Also return "
    "watch: the 2-4 KPIs from the packet that DECIDE the trade — name the metric and the direction that "
    "supports the side (e.g. 'gross margin holds above 35% — supports the long'). Answer ONLY with JSON: "
    '{"points": ["..."], "watch": ["..."]}'
)

# How much filed text the packet may carry (the exhibit + MD&A can be long).
_PACK_FACT_LIMIT = 10
_EXHIBIT_CHARS = 1400


def _pack_path(ticker: str):
    from ptm.config import data_dir

    return data_dir("raw", "research", f"{ticker}.json")


def _pack_inputs(ticker: str) -> dict | None:
    """Fresh filed facts for the packet: last exhibit, consensus changes, forward MD&A lines."""
    path = _pack_path(ticker)
    if not path.exists():
        return None
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    out = {"run_date": str(pack.get("run_date") or "")}
    exhibit = str(pack.get("earnings_exhibit") or "").strip()
    if exhibit:
        out["last_earnings_exhibit"] = exhibit[:_EXHIBIT_CHARS]
    changes = [str(c).strip() for c in (pack.get("reported_changes") or []) if str(c).strip()]
    if changes:
        out["reported_consensus_changes"] = changes[:6]
    # Reuse the main process's fact extractor: it tags forward guidance/backlog
    # sentences ahead of realised changes, which is exactly the next-print cut.
    try:
        from ptm.llm import _sized_facts

        text = " ".join([str(pack.get("mda") or ""), exhibit, " ".join(changes)])
        facts = _sized_facts(text, limit=_PACK_FACT_LIMIT)
        if facts:
            out["filed_facts"] = facts
    except Exception:
        pass
    return out


_WEB_SNIPPET_CHARS = 220
_WEB_RESULTS_PER_QUERY = 5


def _web_inputs(ticker: str, qrow: dict) -> dict | None:
    """Two bounded Ollama web searches: what happened since the pack was filed.

    Snippets only (no page fetches) and every failure degrades to running
    without — the print brief must never die on a dead search endpoint."""
    try:
        from ptm.deepsearch.web import available, web_search
    except Exception:
        return None
    if not available():
        return None
    name = str(qrow.get("name") or "").strip()
    who = f"{name} {ticker}".strip()
    queries = [
        f"{who} guidance outlook latest news",
        f"{ticker} earnings preview analysts expectations",
    ]
    out: dict = {"searches": []}
    for q in queries:
        try:
            results = web_search(q, max_results=_WEB_RESULTS_PER_QUERY)
        except Exception as exc:
            log(f"print brief {ticker}: web search failed ({str(exc)[:60]}) — continuing without it")
            continue
        for r in results[:_WEB_RESULTS_PER_QUERY]:
            title = (r.get("title") or "").strip()
            snippet = (r.get("content") or "").strip()[:_WEB_SNIPPET_CHARS]
            if title or snippet:
                out["searches"].append({"title": title, "snippet": snippet})
    return out or None


def _key(ticker: str, ref: date) -> str:
    path = _pack_path(ticker)
    mtime = int(path.stat().st_mtime) if path.exists() else 0
    return f"v1|{ref.isoformat()}|{mtime}"


def print_brief(ticker: str, side: str | None, member: dict, qrow: dict, theme_row: dict, peer_prints: list[dict], ref: date) -> dict | None:
    """{points, watch} for one member's next print, cached per run date + pack version.

    `side` is "long"/"short" when the name's own revisions carry a side, or None
    for a flat/no-side member — then the brief is side-neutral: what the print
    would reveal that CREATES a side. Returns None when there is nothing to
    brief from (no LLM)."""
    from ptm_simple.brief import _reported_quarter

    cache = simple_dir("print_briefs", f"{ticker}.json")
    key = _key(ticker, ref)
    if cache.exists():
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if saved.get("key") == key and (saved.get("points") or saved.get("watch")):
                return {"points": saved.get("points") or [], "watch": saved.get("watch") or []}
        except Exception:
            pass
    if not llm_available():
        return None

    side_up = "LONG" if side == "long" else "SHORT" if side == "short" else "NONE YET (flat)"
    print_date = member.get("earnings_date") or "unknown"
    reported_q = _reported_quarter(print_date)
    rev90 = member.get("rev90")
    lines = [
        f"Today: {ref.isoformat()}",
        f"Candidate: {ticker} ({side_up})",
        f"Next print: {print_date} ({member.get('days_to_print') or '?'}d)"
        + (f" — it REPORTS {reported_q}" if reported_q else "")
        + "; every quarter that ended before today is already public and is a fact, not a question",
    ]
    if side:
        lines.append(
            f"Own estimates: rev90 {rev90:+.2f}%"
            + (f", analysts up/down 30d: {member.get('up30')}/{member.get('down30')}" if member.get("up30") is not None else "")
            + f" — the side follows the name's own revision direction"
        )
    else:
        if rev90 is not None:
            lines.append(
                f"Own estimates: rev90 {rev90:+.2f}%"
                + (f", analysts up/down 30d: {member.get('up30')}/{member.get('down30')}" if member.get("up30") is not None else "")
                + " — NO SIDE: |rev90| <= 0.5%"
            )
        else:
            lines.append("Own estimates: none cached — NO SIDE and no revision data")
        lines.append(
            "Side-neutral brief: state what the print would reveal that would CREATE a long side "
            "(revisions breaking above +0.5%) or a short side (below -0.5%); the watch KPIs should say "
            "which direction establishes or kills each side"
        )
    if qrow:
        lines.append(
            f"Consensus: FY1 EPS {qrow.get('eps1')}, FY2 {qrow.get('eps2')}, EG1 {qrow.get('eg1')}, "
            f"EG2 {qrow.get('eg2')}, PE1 {qrow.get('pe1')}, PEG1 {qrow.get('peg1')}, P/S {qrow.get('ps')}"
        )
        flag = qrow.get("flag")
        if flag and flag != "n/a":
            lines.append(f"Valuation flag vs theme: {flag} ({qrow.get('flag_detail')}) — the group review will judge this; "
                         "your brief supplies the forward case it is judged against")
    theme = theme_row.get("theme") or ""
    lines.append(
        f"Theme: {theme} — status {theme_row.get('status')}, lean {theme_row.get('lean')} "
        f"(breadth {theme_row.get('breadth', 0):+.2f})"
        + (f"; thesis: {str(theme_row.get('thesis') or '')[:220]}" if theme_row.get("thesis") else "")
    )
    if theme_row.get("bellwether"):
        lines.append(f"Theme bellwether printing within 14 days: {theme_row['bellwether']}")
    peers = [p for p in (peer_prints or []) if p.get("ticker") != ticker and p.get("earnings_date")]
    if peers:
        lines.append("Peer prints (read-through events): " + "; ".join(
            f"{p['ticker']} {p['earnings_date']} ({p.get('days_to_print')}d)" for p in peers[:5]
        ))
    pack = _pack_inputs(ticker)
    if pack:
        lines.append(f"Research pack (EDGAR, run {pack.get('run_date') or 'n/a'}):")
        if pack.get("last_earnings_exhibit"):
            lines.append(f"- Latest earnings exhibit actuals: {pack['last_earnings_exhibit']}")
        for f in pack.get("filed_facts") or []:
            lines.append(f"- {f}")
        for c in pack.get("reported_consensus_changes") or []:
            lines.append(f"- Consensus: {c}")
    else:
        lines.append("Research pack: none cached for this name — work from the consensus and revision data only")
    web = _web_inputs(ticker, qrow)
    if web:
        lines.append("Web search snippets (developments since the filings — recency unverified, leads not dated facts):")
        for s in web["searches"]:
            lines.append(f"- {s['title']}: {s['snippet']}" if s["title"] else f"- {s['snippet']}")
    try:
        out = chat_json(_SYSTEM, "\n".join(lines))
    except Exception as exc:
        log(f"print brief {ticker}: FAIL {str(exc)[:100]}")
        return None
    points = [str(p).strip()[:320] for p in (out.get("points") or []) if str(p).strip()]
    watch = [str(w).strip()[:160] for w in (out.get("watch") or []) if str(w).strip()]
    if not points and not watch:
        log(f"print brief {ticker}: empty — skipping")
        return None
    cache.write_text(json.dumps({"key": key, "ticker": ticker, "points": points, "watch": watch}, indent=2), encoding="utf-8")
    log(f"print brief {ticker}: {len(points)} point(s), {len(watch)} KPI(s) to watch")
    return {"points": points, "watch": watch}


def load_print_brief(ticker: str, ref: date) -> dict | None:
    """The cached next-print brief for the run date, when present."""
    cache = simple_dir("print_briefs", f"{ticker}.json")
    if not cache.exists():
        return None
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return None
    if saved.get("key") == _key(ticker, ref):
        return {"points": saved.get("points") or [], "watch": saved.get("watch") or []}
    return None