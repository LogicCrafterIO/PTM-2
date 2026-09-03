"""Deterministic theme map from the industries listed on Wikipedia.

Each ticker's company is resolved to its Wikipedia article (via Wikidata,
the structured backbone behind Wikipedia's infobox), and the article's
`industry` property (Wikidata P452 — the field Wikipedia's company infobox
renders) becomes its theme. No LLM: a plain, batched API walk, cached per
ticker. Failed requests are NEVER cached — only a resolved answer is.

Fallback chain per ticker, each marked in the cache:
  1. Wikidata P452 via the enwiki sitelink      (source: "wiki-infobox")
  2. Wikidata P452 via entity search            (source: "wiki-search")
  3. industry from the fundamentals table — itself filled from the curated
     index-membership table when a rebuilt row carries none
                                                (source: "yfinance")

The output has the same shape as the manual xlsx theme map, so the radar,
selection and gatekeeping run unchanged on either source.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ptm.log import log
from ptm_simple import simple_dir

_WIKI_API = "https://www.wikidata.org/w/api.php"
_UA = "ptm-simple-theme-map/0.1 (local research tool; contact: local)"
_INDUSTRY_PROP = "P452"
_MIN_LABEL_LEN = 4
# Wikipedia industry properties sometimes carry classification artifacts
# rather than industries; these never make a theme.
_LABEL_STOPLIST = {"international standard industrial classification", "standard industrial classification"}
_BATCH = 50
# The entity-search fallback is the most rate-limited endpoint of the walk;
# cap its wall time per build so one pass cannot grind for an hour. Unreached
# names are never cached — the next build retries them and, meanwhile, the
# map falls back to those tickers' yfinance industries.
_SEARCH_BUDGET_S = 420
# Wikimedia rate-limits per IP (HTTP 429). A global minimum spacing between
# requests — not per-call-site sleeps — is what keeps a ~1500-name build
# under the limit while the search fallback loops ticker by ticker.
_MIN_INTERVAL_S = 1.2
_last_request_mono = 0.0


def _pace() -> None:
    """Sleep until at least _MIN_INTERVAL_S after the previous request began."""
    global _last_request_mono
    wait = _MIN_INTERVAL_S - (time.monotonic() - _last_request_mono)
    if wait > 0:
        time.sleep(wait)
    _last_request_mono = time.monotonic()


def _get(params: dict, retries: int = 6) -> dict | None:
    import urllib.parse
    import urllib.request

    url = f"{_WIKI_API}?{urllib.parse.urlencode(params)}"
    delay = 2.0
    for attempt in range(retries):
        _pace()
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            wait = getattr(exc, "hdrs", {}).get("Retry-After") if hasattr(exc, "hdrs") else None
            wait_s = float(wait) if wait and str(wait).isdigit() else delay
            if attempt == retries - 1:
                log(f"wikidata request failed after {retries} tries: {exc}")
                return None
            time.sleep(wait_s + 0.5)
            delay = min(delay * 2, 30.0)
    return None


def _fundamentals_table() -> "pd.DataFrame | None":
    """The curated fundamentals table, via the configured data root."""
    import pandas as pd

    from ptm.config import data_dir

    path = data_dir("curated", "yahoo_fundamentals.csv")
    if not path.exists():
        return None
    return pd.read_csv(path)


def _index_meta() -> dict[str, tuple[str, str]]:
    """Ticker -> (sector, industry) from the curated index-membership table.

    fundamentals.py's rule is that sector/industry come from "the index
    membership tables, not a data vendor" — the same table the original ingest
    filled the fundamentals CSV's industry column from. Read here so a rebuilt
    row (EDGAR-first, no vendor meta) still has a classification to fall back
    on, in the map build and in the radar alike."""
    import pandas as pd

    from ptm.config import data_dir

    path = data_dir("curated", "universe.csv")
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    out: dict[str, tuple[str, str]] = {}
    for r in df.itertuples():
        sector = getattr(r, "sector", None)
        industry = getattr(r, "industry", None)
        sector = str(sector) if sector is not None and sector == sector else ""
        industry = str(industry) if industry is not None and industry == industry else ""
        if sector or industry:
            out[str(r.ticker).upper()] = (sector, industry)
    return out


def _names() -> dict[str, str]:
    """Ticker -> company name, from the curated fundamentals table."""
    df = _fundamentals_table()
    if df is None:
        return {}
    return {str(r.ticker).upper(): str(r.name) for r in df.itertuples() if isinstance(r.name, str) and r.name}


def _yf_industries() -> dict[str, str]:
    """Ticker -> industry, from the fundamentals table with an index-table fallback.

    The fundamentals table is the fallback peer-group source when Wikidata has
    no industry for a name. A row rebuilt EDGAR-first carries no industry of
    its own, so blank rows are filled from the curated index table — otherwise
    the ticker walk silently shrinks to whichever names an older cache still
    classified (that shrink is how a 1295-ticker build became 62)."""
    df = _fundamentals_table()
    if df is None:
        return {}
    out = {str(r.ticker).upper(): str(r.industry)
           for r in df.itertuples() if isinstance(r.industry, str) and r.industry}
    blank = sorted({str(r.ticker).upper() for r in df.itertuples()
                    if not (isinstance(r.industry, str) and r.industry)})
    if blank:
        meta = _index_meta()
        filled = 0
        for t in blank:
            industry = (meta.get(t) or ("", ""))[1]
            if industry:
                out[t] = industry
                filled += 1
        if blank and filled < len(blank):
            from ptm.log import log

            log(f"wiki industries: {len(blank) - filled} ticker(s) have no industry "
                f"in the fundamentals table or the index table — they cannot be walked")
    return out


def _chunk(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _key(title: str) -> str:
    """Case/whitespace-insensitive comparison key for a title."""
    return " ".join(title.strip().lower().split())


# Corporate suffixes the fundamentals names carry and article titles drop.
# ("Atlas Energy Solutions, Inc." vs the article "Atlas Energy Solutions".)
_SUFFIX_RE = re.compile(
    r"[,\s]+(inc\.?|incorporated|corp\.?|corporation|company|co\.?|ltd\.?|limited|plc|llc"
    r"|holdings?|s\.a\.?|n\.v\.?|ag|gmbh|sa|nv)\s*$",
    flags=re.IGNORECASE,
)


def _variants(name: str) -> list[str]:
    """Plausible enwiki article titles for a company name: the name itself
    plus suffix-stripped and '&'<->'and' forms. Never empty."""
    base = name.strip()
    seen: dict[str, str] = {}
    out: list[str] = []
    candidates = [base]
    stripped = _SUFFIX_RE.sub("", base).strip(" ,.")
    if stripped and stripped.lower() != base.lower():
        candidates.append(stripped)
        if re.search(r"\band\b", stripped, flags=re.IGNORECASE):
            candidates.append(re.sub(r"\band\b", "&", stripped, flags=re.IGNORECASE))
    for cand in candidates:
        key = _key(cand)
        if key and key not in seen:
            seen[key] = cand
            out.append(cand)
    return out or [base]


def _resolve_titles(names: list[str]) -> dict[str, str]:
    """{company name: QID} via enwiki sitelinks, batched.

    Each name is queried under its exact title AND its derived variants
    (see _variants). A derived variant is credited to a name only when the
    variant is unique to that name among all wanted names and is not
    another name's exact title, so two companies collapsing onto one
    string can never share a wrong QID — those fall through to search.
    """
    wanted = sorted(set(names))
    variants_by_name: dict[str, list[str]] = {name: _variants(name) for name in wanted}
    wanted_keys = {_key(n) for n in wanted}
    owner_of: dict[str, str] = {}  # derived-variant key -> owner, unique only
    for name in wanted:
        for variant in variants_by_name[name][1:]:
            key = _key(variant)
            if key in wanted_keys:
                continue  # another name's exact title: let that exact request resolve it
            if key in owner_of and owner_of[key] != name:
                owner_of[key] = ""  # contested: no one may use it
            elif key not in owner_of:
                owner_of[key] = name
    owner_of = {k: v for k, v in owner_of.items() if v}

    # titles to request, in original case, each tagged with the name its
    # answer resolves: exact names to themselves, unique variants to their owner
    req_titles: list[str] = []
    seen: set[str] = set()
    title_owner: dict[str, str] = {}
    for name in wanted:
        for title in [name] + [v for v in variants_by_name[name][1:] if _key(v) in owner_of]:
            key = _key(title)
            title_owner.setdefault(key, name)
            if key not in seen:
                seen.add(key)
                req_titles.append(title)

    out: dict[str, str] = {}
    batches = list(_chunk(req_titles, _BATCH))
    for i, batch in enumerate(batches):
        out_raw = _get({
            "action": "wbgetentities", "sites": "enwiki", "titles": "|".join(batch),
            "props": "sitelinks", "sitefilter": "enwiki", "format": "json",
        }) or {}
        title_qid: dict[str, str] = {}  # comparison key of a title -> QID
        for qid, payload in (out_raw.get("entities") or {}).items():
            if not str(qid).startswith("Q"):
                continue  # "-1" carries the missing ones
            site = (payload.get("sitelinks") or {}).get("enwiki") or {}
            title = site.get("title")
            if title:
                title_qid[_key(title)] = qid
        for norm in (out_raw.get("normalized") or []):
            # normalization moved a requested title (case/unicode); the answer
            # sits under the normalized form — try it for the same owner
            frm, to = _key(norm.get("from", "")), _key(norm.get("to", ""))
            if frm in title_owner and to in title_qid:
                out.setdefault(title_owner[frm], title_qid[to])
        for title in batch:
            qid = title_qid.get(_key(title))
            owner = title_owner.get(_key(title))
            if qid and owner:
                out.setdefault(owner, qid)
        log(f"wiki titles: batch {i + 1}/{len(batches)} — {len(out)} names resolved so far")
        time.sleep(0.2)
    return out


def _search_qid(name: str) -> str | None:
    out = _get({
        "action": "wbsearchentities", "search": name, "language": "en",
        "type": "item", "limit": 1, "format": "json",
    })
    hits = (out or {}).get("search") or []
    return hits[0]["id"] if hits else None


def _claims_for(qids: list[str]) -> dict[str, list[str]]:
    """{QID: [industry QIDs]} via P452, batched."""
    result: dict[str, list[str]] = {}
    batches = list(_chunk(sorted(set(qids)), 50))
    for i, batch in enumerate(batches):
        out = _get({
            "action": "wbgetentities", "ids": "|".join(batch), "props": "claims",
            "format": "json",
        })
        for qid, payload in ((out or {}).get("entities") or {}).items():
            claims = payload.get("claims", {}).get(_INDUSTRY_PROP) or []
            vals = []
            for c in claims:
                snak = c.get("mainsnak") or {}
                val = (snak.get("datavalue") or {}).get("value") or {}
                if isinstance(val, dict) and val.get("id"):
                    vals.append(val["id"])
            if vals:
                result[qid] = vals
        if i % 5 == 4 or i == len(batches) - 1:
            log(f"wiki claims: batch {i + 1}/{len(batches)}")
        time.sleep(0.2)
    return result


def _industry_labels(qids: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    batches = list(_chunk(qids, 50))
    for i, batch in enumerate(batches):
        out = _get({
            "action": "wbgetentities", "ids": "|".join(batch), "props": "labels",
            "languages": "en", "format": "json",
        })
        for qid, payload in ((out or {}).get("entities") or {}).items():
            label = (payload.get("labels") or {}).get("en", {}).get("value")
            if label:
                labels[qid] = label
        if i % 5 == 4 or i == len(batches) - 1:
            log(f"wiki labels: batch {i + 1}/{len(batches)}")
        time.sleep(0.2)
    return labels


def wiki_industries(tickers: list[str], names: dict[str, str], sleep_s: float = 0.1) -> dict[str, dict]:
    """{ticker: {industries, source, matched, qid}} — cached per ticker.

    Failures are never cached: only a resolved answer (industries found, or a
    confirmed missing industry on a resolved entity) is persisted, so a
    rate-limit blip retried later cannot poison the map.
    """
    cache_dir = simple_dir("wiki_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict] = {}
    pending: list[str] = []
    for ticker in tickers:
        cache = cache_dir / f"{ticker}.json"
        if cache.exists():
            try:
                out[ticker] = json.loads(cache.read_text(encoding="utf-8"))
                continue
            except Exception:
                pass
        pending.append(ticker)
    if not pending:
        return out

    # 1) bulk-resolve by Wikipedia article title (plus suffix variants)
    title_to_qid = _resolve_titles([names.get(t, t) for t in pending])
    ticker_qid: dict[str, str] = {}
    unresolved: list[str] = []
    for ticker in pending:
        name = names.get(ticker) or ticker
        qid = title_to_qid.get(name)
        if qid:
            ticker_qid[ticker] = qid
        else:
            unresolved.append(ticker)
    # 2) search fallback for the misses (1 call each, cached afterwards).
    #    The search endpoint is far more heavily rate-limited than entity
    #    lookups, so the fallback runs under a wall-time budget: whatever it
    #    does not reach stays uncached (a later build retries it) and the map
    #    fills those names from yfinance industries meanwhile.
    search_deadline = time.monotonic() + _SEARCH_BUDGET_S
    searched = 0
    for i, ticker in enumerate(unresolved):
        if time.monotonic() > search_deadline:
            log(f"wiki search budget spent after {searched} lookups; "
                f"{len(unresolved) - i} names left to the yfinance fallback / a later build")
            break
        qid = _search_qid(names.get(ticker) or ticker)
        searched += 1
        if qid:
            ticker_qid[ticker] = qid
        if (i + 1) % 25 == 0:
            log(f"wiki search fallback: {i + 1}/{len(unresolved)}")
        time.sleep(max(sleep_s, 0.15))

    industry_qids = _claims_for(list(ticker_qid.values()))
    labels = _industry_labels([q for qs in industry_qids.values() for q in qs])
    for ticker in pending:
        name = names.get(ticker) or ticker
        qid = ticker_qid.get(ticker)
        if not qid:
            continue  # unresolved: not cached, retried next build
        inds = industry_qids.get(qid) or []
        industries = [labels[q] for q in inds if q in labels]
        source = "wiki-infobox" if industries else "wikidata-no-industry"
        rec = {"qid": qid, "matched": name, "industries": industries, "source": source}
        out[ticker] = rec
        (cache_dir / f"{ticker}.json").write_text(json.dumps(rec), encoding="utf-8")
    log(f"wiki industries: {sum(1 for r in out.values() if r['industries'])} of {len(tickers)} resolved "
        f"({len(pending)} fresh this pass)")
    return out


def dedupe_memberships(themes: list[dict]) -> list[dict]:
    """One membership per ticker: it stays only in its LARGEST theme.

    Wikidata's industry property (P452) is multi-valued — a broad company like
    Salesforce carries nine labels, and a map that keeps every label ranks the
    same fundamentals once per label (28% of one sweep's LLM work went to
    repeat appearances, and six names landed twice on one leaderboard). The
    largest group a name belongs to is also the most informative peer median
    for it, so the tie-break is deterministic: bigger theme wins, alphabetical
    label on a tie. Themes are the labels themselves; only memberships shrink,
    so a theme every one of whose members carries elsewhere simply empties."""
    sizes = {t["theme"]: len(t["members"]) for t in themes}
    best: dict[str, str] = {}
    for t in themes:
        for m in t["members"]:
            cur = best.get(m)
            if cur is None or sizes[t["theme"]] > sizes[cur] or (
                    sizes[t["theme"]] == sizes[cur] and t["theme"] < cur):
                best[m] = t["theme"]
    kept = []
    for t in themes:
        members = sorted(m for m in t["members"] if best.get(m) == t["theme"])
        if members:
            kept.append({**t, "members": members})
    return kept


def build_theme_map_wiki(tickers: list[str] | None = None, min_members: int = 1) -> dict:
    """Theme map from Wikipedia industries, same shape as the manual map.

    `min_members` defaults to 1: an industry Wikipedia does resolve but that
    holds fewer than three names is KEPT as a theme and judged in isolation —
    the ranking pass reads the same fundamental packet (revisions, surprise
    record, consensus growth, absolute forward P/E / PEG / P/S) with no peer
    median and no read-throughs, because a lone member is still a judgeable
    forward case. Pass a higher `min_members` to drop those themes again.
    """
    names = _names()
    if not tickers:
        tickers = sorted(_yf_industries())
    resolved = wiki_industries(tickers, names)
    yf = _yf_industries()
    by_label: dict[str, dict] = {}
    fallbacks = 0
    for ticker in tickers:
        rec = resolved.get(ticker) or {}
        industries = rec.get("industries") or []
        source = rec.get("source", "none")
        if not industries and yf.get(ticker):
            industries, source, fallbacks = [yf[ticker]], "yfinance", fallbacks + 1
        for label in industries:
            key = label.strip().lower()
            if len(key) < _MIN_LABEL_LEN or key in _LABEL_STOPLIST:
                continue
            entry = by_label.setdefault(key, {"label": label.strip(), "members": [], "sources": set()})
            if ticker not in entry["members"]:
                entry["members"].append(ticker)
            entry["sources"].add("yfinance" if source == "yfinance" else "wikipedia")
    themes = []
    for key in sorted(by_label):
        entry = by_label[key]
        if len(entry["members"]) < min_members:
            continue
        themes.append({
            "theme": entry["label"],
            "members": sorted(entry["members"]),
            "thesis": "",
            "source": sorted(entry["sources"]),
        })
    # One membership per ticker (see dedupe_memberships): Wikipedia labels a
    # broad company with several industries, and ranking the same fundamentals
    # once per label is duplicate work with duplicate leaderboard entries.
    themes = dedupe_memberships(themes)
    reverse: dict[str, list[str]] = {}
    for t in themes:
        for m in t["members"]:
            reverse.setdefault(m, []).append(t["theme"])
    out = {
        "source": "wikipedia-industry",
        "built_at": time.time(),
        "theme_count": len(themes),
        "ticker_count": len(reverse),
        "wiki_fallbacks": fallbacks,
        "min_members": min_members,
        "themes": themes,
        "ticker_themes": {k: sorted(v) for k, v in sorted(reverse.items())},
    }
    path = simple_dir("theme_map_wiki.json")
    from ptm.io import write_json

    write_json(path, out)
    small = sum(1 for t in themes if len(t["members"]) < 3)
    log(f"wiki theme map: {out['theme_count']} themes ({small} below 3 members, kept for isolated "
        f"judging), {out['ticker_count']} tickers ({fallbacks} yfinance fallbacks) -> {path}")
    return out