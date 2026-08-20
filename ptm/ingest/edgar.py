"""SEC EDGAR companyfacts + recent 10-K/10-Q text."""

from __future__ import annotations

import re
import time
from datetime import datetime
from threading import Lock
import warnings
from functools import lru_cache

import requests
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning

from ptm.asof import as_of_date, is_backdated
from ptm.config import data_dir, env
from ptm.io import read_json, write_json

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

TICKERS_URLS = (
    "https://www.sec.gov/files/company_tickers.json",
    "https://data.sec.gov/files/company_tickers.json",
)
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{primary}"
INDEX_JSON = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
# SEC's published ceiling is 10 requests/second for a declared User-Agent.
SEC_MAX_RPS = 8


def _headers() -> dict:
    return {
        "User-Agent": env().sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/html, */*",
    }



# --- SEC rate limiting -------------------------------------------------------
# SEC asks for no more than 10 requests/second with a declaring User-Agent. A
# shared token bucket lets several worker threads fetch concurrently while the
# process as a whole stays inside that budget - far faster than one thread
# sleeping between every call, and still a good citizen.

_RATE_LOCK = Lock()
_LAST_CALL = [0.0]


def _rate_limited() -> None:
    """Block until this process may issue another SEC request."""
    min_gap = 1.0 / float(SEC_MAX_RPS)
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _LAST_CALL[0] + min_gap - now
        if wait > 0:
            time.sleep(wait)
            now = now + wait
        _LAST_CALL[0] = now


def sec_get(url: str, **kwargs):
    """requests.get against SEC, throttled to the shared budget."""
    _rate_limited()
    return requests.get(url, headers=_headers(), **kwargs)


@lru_cache
def ticker_map() -> dict[str, str]:
    cache = data_dir("curated", "sec_tickers.json")
    if cache.exists():
        return {k: str(v) for k, v in read_json(cache).items()}
    for url in TICKERS_URLS:
        try:
            response = sec_get(url, timeout=30)
            response.raise_for_status()
            payload = response.json()
            break
        except Exception:
            payload = None
    else:
        return {}
    mapping = {}
    for item in payload.values():
        ticker = str(item.get("ticker", "")).upper().replace(".", "-")
        cik = str(item.get("cik_str", "")).zfill(10)
        if ticker and cik:
            mapping[ticker] = cik
    write_json(cache, mapping)
    return mapping


def _visible_facts(series: list[dict]) -> list[dict]:
    """XBRL rows the run date could have seen.

    A fact is knowable only once its filing is public, so a backdated run keys
    off `filed`, not `end` — a Q2 number with end=2026-06-30 filed 2026-08-05 is
    invisible to a 2026-07-15 run.
    """
    if not is_backdated():
        return series
    cutoff = as_of_date().isoformat()
    return [row for row in series if str(row.get("filed") or "")[:10] <= cutoff]


def _unit_series(facts: dict, taxonomy: str, tag: str, unit: str | None = None) -> list[dict]:
    node = facts.get("facts", {}).get(taxonomy, {}).get(tag, {})
    units = node.get("units", {})
    if unit:
        series = units.get(unit)
    else:
        series = units.get("USD") or units.get("USD/shares") or next(iter(units.values()), None)
    return list(series or [])


def _latest_fact(facts: dict, taxonomy: str, tag: str) -> float | None:
    series = _visible_facts(_unit_series(facts, taxonomy, tag))
    annual = [row for row in series if row.get("form") in {"10-K", "10-Q"} and row.get("val") is not None]
    if not annual:
        return None
    annual.sort(key=lambda row: (row.get("end") or "", row.get("filed") or ""), reverse=True)
    return float(annual[0]["val"])


def company_facts(ticker: str) -> dict:
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return {"ticker": ticker, "error": "no CIK"}
    cache = data_dir("raw", "edgar", f"{ticker}_facts{_asof_suffix()}.json")
    if cache.exists():
        return read_json(cache)
    # The fundamentals build already pulled these exact lines out of companyfacts
    # and cached the small extract. Reuse it rather than re-downloading a
    # multi-megabyte document once per idea.
    prebuilt = data_dir("raw", "edgar", f"{ticker}_fundamentals{_asof_suffix()}.json")
    if prebuilt.exists():
        try:
            payload = read_json(prebuilt)
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("ticker"):
            extracted = {
                "ticker": ticker,
                "cik": cik,
                **{
                    key: payload.get(key)
                    for key in ("revenue", "net_income", "ebit", "cash", "debt", "assets", "equity", "interest")
                },
            }
            write_json(cache, extracted)
            return extracted
    url = FACTS_URL.format(cik=cik)
    response = sec_get(url, timeout=45)
    if response.status_code >= 400:
        payload = {"ticker": ticker, "cik": cik, "error": response.status_code}
        write_json(cache, payload)
        return payload
    facts = response.json()
    extracted = {
        "ticker": ticker,
        "cik": cik,
        "revenue": _latest_fact(facts, "us-gaap", "Revenues")
        or _latest_fact(facts, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        "net_income": _latest_fact(facts, "us-gaap", "NetIncomeLoss"),
        "ebit": _latest_fact(facts, "us-gaap", "OperatingIncomeLoss"),
        "cash": _latest_fact(facts, "us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        "debt": _latest_fact(facts, "us-gaap", "LongTermDebt")
        or _latest_fact(facts, "us-gaap", "LongTermDebtNoncurrent"),
        "assets": _latest_fact(facts, "us-gaap", "Assets"),
        "equity": _latest_fact(facts, "us-gaap", "StockholdersEquity"),
        "interest": _latest_fact(facts, "us-gaap", "InterestExpense"),
    }
    write_json(cache, extracted)
    return extracted


COVER_MARKERS = ("iso4217:usd", "xbrli:shares", "form 8-k current report", "item 9.01")
EARNINGS_HINTS = ("exhibit 99", "earnings release", "press release", "net income", "earnings per share", "financial results")
_ITEM_HEADING = re.compile(r"Item\s+\d+[A-Z]?[\.\s]", re.I)


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" "))


def _is_toc_chunk(chunk: str, heading_len: int) -> bool:
    """True when the hit is a table-of-contents line (heading + page number)."""
    body = chunk[heading_len:] if heading_len <= len(chunk) else chunk
    nxt = _ITEM_HEADING.search(body)
    span = (body[: nxt.start()] if nxt else body).strip()
    if len(span) > 160:
        return False
    return bool(re.search(r"\d{1,4}\s*$", span)) and not re.search(r"[.!?].{20,}", span)


def is_cover_page(text: str) -> bool:
    low = (text or "").lower()
    if not any(marker in low for marker in COVER_MARKERS):
        return False
    if any(hint in low for hint in EARNINGS_HINTS):
        return False
    return True


def is_exhibit99_name(name: str) -> bool:
    low = (name or "").lower().replace("_", "-")
    return any(token in low for token in ("ex99", "ex-99", "exhibit99", "exhibit-99"))


def _section(text: str, start: str, end: str, limit: int, min_body: int = 40) -> str:
    for match in re.finditer(start, text, flags=re.I):
        rest = text[match.start() :]
        closer = re.search(end, rest[30:], flags=re.I)
        chunk = rest[: closer.start() + 30] if closer else rest
        chunk = chunk[:limit].strip()
        heading_len = match.end() - match.start()
        if _is_toc_chunk(chunk, heading_len):
            continue
        if len(chunk) < min_body:
            continue
        return chunk
    return ""


def extract_filing_sections(text: str, max_chars: int = 4000) -> dict[str, str]:
    business = _section(
        text,
        r"Item\s+1[\.\s]+Business",
        r"Item\s+1A[\.\s]+Risk",
        max_chars,
    )
    mda = _section(
        text,
        r"Item\s+7[\.\s]+Management.?s Discussion",
        r"Item\s+7A[\.\s]+",
        max_chars,
        min_body=200,
    )
    if len(mda) < 200:
        q_mda = _section(
            text,
            r"Item\s+2[\.\s]+Management.?s Discussion",
            r"Item\s+3[\.\s]+",
            max_chars,
            min_body=200,
        )
        if len(q_mda) > len(mda):
            mda = q_mda
    return {"business": business, "mda": mda}


def _fetch_doc(cik: str, acc: str, primary: str, timeout: int = 45) -> str:
    url = ARCHIVES.format(cik=int(cik), acc=acc.replace("-", ""), primary=primary)
    doc = requests.get(url, headers=_headers(), timeout=timeout)
    if doc.status_code >= 400:
        return ""
    return doc.text


def latest_filing_text(ticker: str, forms: tuple[str, ...] = ("10-K", "10-Q"), max_chars: int = 12000) -> str:
    sections = filing_sections(ticker, max_chars=max_chars // 2)
    parts = [sections.get("business") or "", sections.get("mda") or ""]
    blob = "\n\n".join(p for p in parts if p)
    if blob:
        return blob[:max_chars]
    cache = data_dir("raw", "edgar", f"{ticker}_filing{_asof_suffix()}.txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    return ""




def _neg_date(value: str) -> str:
    """Sort key that puts the newest ISO date first."""
    digits = "".join(ch for ch in str(value)[:10] if ch.isdigit())
    if len(digits) != 8:
        return "99999999"
    return str(99999999 - int(digits)).zfill(8)


def _asof_suffix() -> str:
    """Keep backdated caches separate; a live cache holds newer filings."""
    return f"_{as_of_date().isoformat()}" if is_backdated() else ""


def _filed_on_or_before(recent: dict, index: int) -> bool:
    """True when filing `index` was public by the run date."""
    if not is_backdated():
        return True
    dates = recent.get("filingDate") or []
    if index >= len(dates):
        return False
    return str(dates[index])[:10] <= as_of_date().isoformat()


def _visible_rows(recent: dict, *keys: str) -> list[tuple]:
    """Zip the requested `recent` columns, dropping anything filed after the run date."""
    columns = [recent.get(key) or [] for key in keys]
    if not columns or not columns[0]:
        return []
    length = min(len(col) for col in columns)
    return [
        tuple(col[i] for col in columns)
        for i in range(length)
        if _filed_on_or_before(recent, i)
    ]


def _cache_sections_usable(payload: dict) -> bool:
    business = str(payload.get("business") or "")
    mda = str(payload.get("mda") or "")
    return len(business.strip()) >= 40 or len(mda.strip()) >= 200


def filing_sections(ticker: str, max_chars: int = 4000) -> dict[str, str]:
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return {"business": "", "mda": ""}
    cache = data_dir("raw", "edgar", f"{ticker}_sections{_asof_suffix()}.json")
    if cache.exists():
        cached = read_json(cache)
        if _cache_sections_usable(cached):
            return cached
    url = SUBMISSIONS_URL.format(cik=cik)
    response = sec_get(url, timeout=45)
    if response.status_code >= 400:
        return {"business": "", "mda": ""}
    recent = response.json().get("filings", {}).get("recent", {})
    pairs = _visible_rows(recent, "form", "accessionNumber", "primaryDocument")
    ordered = [row for row in pairs if row[0] == "10-K"] + [row for row in pairs if row[0] == "10-Q"]
    extracted = {"business": "", "mda": ""}
    last_text = ""
    for form, acc, primary in ordered:
        html = _fetch_doc(cik, acc, primary)
        if not html:
            continue
        text = _strip_html(html)
        last_text = text
        got = extract_filing_sections(text, max_chars=max_chars)
        if len(got.get("business") or "") > len(extracted["business"]):
            extracted["business"] = got["business"]
        if len(got.get("mda") or "") > len(extracted["mda"]) and len(got.get("mda") or "") >= 200:
            extracted["mda"] = got["mda"]
        if len(extracted["business"]) >= 400 and len(extracted["mda"]) >= 200:
            break
        time.sleep(0.2)
    if _cache_sections_usable(extracted):
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_json(cache, extracted)
        if last_text:
            raw = data_dir("raw", "edgar", f"{ticker}_filing{_asof_suffix()}.txt")
            raw.write_text(last_text[: max_chars * 4], encoding="utf-8", errors="ignore")
    return extracted


def latest_earnings_exhibit(ticker: str, max_chars: int = 5000) -> str:
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return ""
    cache = data_dir("raw", "edgar", f"{ticker}_ex99{_asof_suffix()}.txt")
    if cache.exists():
        cached = cache.read_text(encoding="utf-8", errors="ignore")
        if cached and not is_cover_page(cached):
            return cached[:max_chars]
    url = SUBMISSIONS_URL.format(cik=cik)
    response = sec_get(url, timeout=45)
    if response.status_code >= 400:
        return ""
    recent = response.json().get("filings", {}).get("recent", {})
    if not recent.get("items"):
        recent = {**recent, "items": [""] * len(recent.get("form") or [])}
    indexed = _visible_rows(recent, "form", "accessionNumber", "primaryDocument", "items", "filingDate")
    # Results-of-operations items first, then strictly newest filing date. Without
    # the date key an old 8-K can win and a 2020 release ends up pricing a 2026
    # screen, which is exactly the bug this ordering prevents.
    indexed.sort(key=lambda row: (0 if "2.02" in str(row[3]) else 1, _neg_date(str(row[4]))))
    for form, acc, _primary, _items, _filed in indexed:
        if not str(form).startswith("8-K"):
            continue
        acc_nodash = acc.replace("-", "")
        index_url = INDEX_JSON.format(cik=int(cik), acc=acc_nodash)
        try:
            index = sec_get(index_url, timeout=20)
            files = (index.json().get("directory") or {}).get("item") or []
        except Exception:
            files = []
        names = [str(item.get("name") or "") for item in files if is_exhibit99_name(str(item.get("name") or ""))]
        for name in names[:3]:
            html = _fetch_doc(cik, acc, name, timeout=30)
            if not html:
                continue
            text = _strip_html(html)
            if len(text) < 200 or is_cover_page(text):
                continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text[: max_chars * 2], encoding="utf-8", errors="ignore")
            time.sleep(0.2)
            return text[:max_chars]
        time.sleep(0.15)
    return ""


# --- point-in-time fundamentals ---------------------------------------------
# Yahoo's `info` is a live snapshot with no history, so a backdated run rebuilds
# what it can from XBRL, where every fact carries the date it became public.

EPS_TAGS = ("EarningsPerShareDiluted", "EarningsPerShareBasic", "IncomeLossFromContinuingOperationsPerDilutedShare")
SHARE_TAGS = (
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
)


def _days_between(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        a = datetime.strptime(str(start)[:10], "%Y-%m-%d").date()
        b = datetime.strptime(str(end)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (b - a).days


def _dedup_periods(rows: list[dict]) -> list[dict]:
    """One row per reporting period, keeping the latest filing visible by the
    run date — i.e. the restatement the desk would actually have had."""
    best: dict[tuple, dict] = {}
    for row in rows:
        key = (str(row.get("start")), str(row.get("end")))
        current = best.get(key)
        if current is None or str(row.get("filed") or "") > str(current.get("filed") or ""):
            best[key] = row
    return sorted(best.values(), key=lambda r: str(r.get("end") or ""), reverse=True)


def eps_windows(facts: dict) -> dict:
    """Trailing-twelve-month diluted EPS and the year before it, as of the run date."""
    rows: list[dict] = []
    for tag in EPS_TAGS:
        series = _visible_facts(_unit_series(facts, "us-gaap", tag, unit="USD/shares"))
        rows = [r for r in series if r.get("val") is not None and r.get("form") in {"10-K", "10-Q"}]
        if rows:
            break
    if not rows:
        return {"ttm": None, "prior_ttm": None, "basis": "none", "last_period_end": None}
    ordered = _dedup_periods(rows)
    quarters = [r for r in ordered if (_days_between(r.get("start"), r.get("end")) or 0) in range(60, 116)]
    annuals = [r for r in ordered if (_days_between(r.get("start"), r.get("end")) or 0) in range(330, 401)]

    def _sum(window: list[dict]) -> float:
        return float(sum(float(r["val"]) for r in window))

    if len(quarters) >= 8:
        return {
            "ttm": _sum(quarters[:4]),
            "prior_ttm": _sum(quarters[4:8]),
            "basis": "4 quarterly filings",
            "last_period_end": str(quarters[0].get("end"))[:10],
        }
    if len(quarters) >= 4 and annuals:
        return {
            "ttm": _sum(quarters[:4]),
            "prior_ttm": float(annuals[0]["val"]),
            "basis": "4 quarters vs prior 10-K",
            "last_period_end": str(quarters[0].get("end"))[:10],
        }
    if len(annuals) >= 2:
        return {
            "ttm": float(annuals[0]["val"]),
            "prior_ttm": float(annuals[1]["val"]),
            "basis": "annual 10-K only (no TTM)",
            "last_period_end": str(annuals[0].get("end"))[:10],
        }
    if annuals:
        return {
            "ttm": float(annuals[0]["val"]),
            "prior_ttm": None,
            "basis": "single 10-K",
            "last_period_end": str(annuals[0].get("end"))[:10],
        }
    return {"ttm": None, "prior_ttm": None, "basis": "insufficient EPS filings", "last_period_end": None}


def shares_outstanding(facts: dict) -> float | None:
    """Latest share count public by the run date."""
    for taxonomy, tag in SHARE_TAGS:
        series = _visible_facts(_unit_series(facts, taxonomy, tag, unit="shares"))
        rows = [r for r in series if r.get("val")]
        if not rows:
            continue
        rows.sort(key=lambda r: (str(r.get("end") or ""), str(r.get("filed") or "")), reverse=True)
        return float(rows[0]["val"])
    return None


def report_dates(ticker: str, limit: int = 8) -> list[str]:
    """Filing dates of recent 10-K/10-Q, newest first, visible at the run date.

    Used to project the *next* earnings date from past cadence rather than from
    Yahoo's calendar, which only ever knows the currently scheduled date.
    """
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return []
    cache = data_dir("raw", "edgar", f"{ticker}_reportdates{_asof_suffix()}.json")
    if cache.exists():
        try:
            return list(read_json(cache))[:limit]
        except Exception:
            pass
    url = SUBMISSIONS_URL.format(cik=cik)
    try:
        response = sec_get(url, timeout=45)
    except Exception:
        return []
    if response.status_code >= 400:
        return []
    recent = response.json().get("filings", {}).get("recent", {})
    rows = _visible_rows(recent, "form", "filingDate")
    dates = sorted(
        {str(filed)[:10] for form, filed in rows if str(form) in {"10-K", "10-Q"}},
        reverse=True,
    )[:limit]
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_json(cache, dates)
    return dates


def raw_company_facts(ticker: str) -> dict:
    """Full XBRL payload, fetched fresh.

    Deliberately NOT cached to disk: companyfacts documents run to several MB
    each, and caching the whole universe would cost gigabytes. Callers should
    take what they need and cache that instead — see company_fundamentals.
    """
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return {}
    url = FACTS_URL.format(cik=cik)
    try:
        response = sec_get(url, timeout=45)
    except Exception:
        return {}
    if response.status_code >= 400:
        return {}
    return response.json()



def extract_max_age_days() -> int:
    """How long a cached XBRL extract stays usable on a live run.

    Backdated runs pin their own vintage and never expire. Live runs must, or a
    company that files a fresh 10-Q is invisible until the cache is cleared by
    hand: the extract is keyed only by ticker, so it would otherwise be returned
    forever. Shorten this during earnings season, when a week of staleness can
    span a whole quarter's results.
    """
    from ptm.config import toml_settings

    cfg = toml_settings().get("edgar") or {}
    return int(cfg.get("extract_max_age_days") or 7)


def _cache_fresh(path) -> bool:
    if not path.exists():
        return False
    if is_backdated():
        # Pinned to a run date, so its contents cannot go stale.
        return True
    max_age = extract_max_age_days()
    if max_age <= 0:
        return True
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    return age_days <= max_age


def company_fundamentals(ticker: str, with_guidance: bool = True) -> dict:
    """Every fundamental the screen needs for one name, from EDGAR alone.

    Share counts, EPS windows and balance-sheet lines all come from XBRL facts
    that were public on the run date; forward EPS comes from the company's own
    guidance in its earnings release when one is parseable. No market data and
    no third-party estimates are involved — price is applied by the caller from
    the price history.

    The small extract is cached per ticker (and per vintage on backdated runs);
    the multi-megabyte source payload is not.
    """
    cache = data_dir("raw", "edgar", f"{ticker}_fundamentals{_asof_suffix()}.json")
    if _cache_fresh(cache):
        try:
            cached = read_json(cache)
            if isinstance(cached, dict) and cached.get("ticker"):
                return cached
        except Exception:
            pass
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    out: dict = {
        "ticker": ticker,
        "cik": cik,
        "shares": None,
        "eps_ttm": None,
        "eps_prior_ttm": None,
        "eps_basis": "no CIK" if not cik else "no XBRL",
        "last_period_end": None,
        "revenue": None,
        "net_income": None,
        "ebit": None,
        "cash": None,
        "debt": None,
        "assets": None,
        "equity": None,
        "interest": None,
        "report_dates": [],
        "guidance": None,
    }
    if not cik:
        write_json(cache, out)
        return out
    facts = raw_company_facts(ticker)
    if facts:
        eps = eps_windows(facts)
        out.update(
            {
                "shares": shares_outstanding(facts),
                "eps_ttm": eps.get("ttm"),
                "eps_prior_ttm": eps.get("prior_ttm"),
                "eps_basis": eps.get("basis"),
                "last_period_end": eps.get("last_period_end"),
                "revenue": _latest_fact(facts, "us-gaap", "Revenues")
                or _latest_fact(facts, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                "net_income": _latest_fact(facts, "us-gaap", "NetIncomeLoss"),
                "ebit": _latest_fact(facts, "us-gaap", "OperatingIncomeLoss"),
                "cash": _latest_fact(facts, "us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
                "debt": _latest_fact(facts, "us-gaap", "LongTermDebt")
                or _latest_fact(facts, "us-gaap", "LongTermDebtNoncurrent"),
                "assets": _latest_fact(facts, "us-gaap", "Assets"),
                "equity": _latest_fact(facts, "us-gaap", "StockholdersEquity"),
                "interest": _latest_fact(facts, "us-gaap", "InterestExpense"),
            }
        )
    try:
        out["report_dates"] = report_dates(ticker)
    except Exception:
        out["report_dates"] = []
    if with_guidance:
        try:
            out["guidance"] = guidance_eps(ticker)
        except Exception:
            out["guidance"] = None
    write_json(cache, out)
    return out


# --- management EPS guidance -------------------------------------------------
# EDGAR carries no analyst estimates — it holds filings, and consensus is
# proprietary. It does sometimes carry the company's OWN guidance, as free text
# in the Exhibit 99.1 earnings release.
#
# That sounds like a clean substitute and is not, for one structural reason:
# guidance is almost always **non-GAAP / adjusted** EPS, while the trailing EPS
# in XBRL is **GAAP**. Dividing a price by an adjusted forward number and then
# comparing the growth against a GAAP trailing number produces a ratio that
# means nothing — AbbVie shows ~$14 adjusted guidance against ~$3.54 GAAP TTM.
# On top of that the free-text extraction is fragile: quarterly figures, prior
# year comparatives and exhibit headers all look like guidance to a regex.
#
# So this is OFF by default (`[edgar] fetch_guidance`). The parser is kept, and
# tightened, for callers that want it with eyes open. See
# docs/FEATURE-LIMITATIONS.md.

_MONEY = r"\$\s*(\d{1,3}(?:\.\d{1,2})?)"
GUIDANCE_CUES = re.compile(
    r"(guidance|outlook|expect\w*|forecast\w*|anticipat\w*|reaffirm\w*|project\w*)",
    re.I,
)
# Guidance is about a future full year, not a quarter just reported.
FULL_YEAR_CUES = re.compile(r"(full[- ]year|full year|fiscal (?:year )?20\d\d|\bFY\s?\d{2,4}\b|for 20\d\d)", re.I)
# Anything that reads as a report of results already delivered.
REPORTED_CUES = re.compile(
    r"(compared (?:to|with)|versus|\bvs\.?\b|quarter ended|year ended|months ended|"
    r"\bQ[1-4]\s?['’]?\d{2}\b|reported (?:diluted |adjusted )?(?:eps|earnings)|"
    r"\bwas\b|\bwere\b|increase of|decrease of|declined|grew)",
    re.I,
)
# "Adjusted Net Income per Diluted Share to $5.25" is EPS guidance, and the
# original pattern did not recognise it - it wanted the literal words "earnings
# per share". Net income per share is the same quantity under a different and
# very common label, so real guidance was being read as no guidance at all.
EPS_CUES = re.compile(
    r"(earnings per (?:diluted )?share|(?:net )?income per (?:diluted |basic )?share|"
    r"per (?:diluted|basic) share|diluted eps|adjusted eps|\bEPS\b)",
    re.I,
)
RANGE_RE = re.compile(rf"{_MONEY}\s*(?:to|-|–|—|through)\s*{_MONEY}", re.I)
# "to" and "at" matter: companies write "raising guidance TO $5.25" at least as
# often as "guidance OF $5.25", and omitting them read real guidance as none.
# Safe to include here because a sentence only reaches this point having already
# cleared the guidance, EPS, full-year, stale-year and reported-results checks.
SINGLE_RE = re.compile(
    rf"(?:of|be|to|at|approximately|about|at least|reaching)\s+{_MONEY}", re.I
)
# Per-share numbers live in single digits; anything larger is revenue or a total.
MAX_PLAUSIBLE_EPS = 60.0


def _is_per_share(sentence: str, match: re.Match) -> bool:
    """Is the figure this match found a per-share number, or a revenue total?

    SMCI's release guided "net sales in the range of $14.5 billion", and the
    parser reported 0.94 EPS against a 4.34 consensus - a 78% miss, from a
    revenue figure. What separates them is the units immediately after the
    number, not anywhere in the sentence: a real guidance sentence often gives
    revenue and EPS side by side.
    """
    tail = sentence[match.end() : match.end() + 24].lower()
    if re.match(r"\s*(billion|million|bn|mm|thousand)", tail):
        return False
    return True


def _mentions_stale_year(sentence: str) -> bool:
    """Does this sentence name a year that has already finished?

    Guidance is about the year ahead. A release discussing "fiscal 2024" or
    "FY 2022 diluted EPS" is recounting history, and the regex cannot tell the
    difference from wording alone - it matched a Cadence acquisition note and a
    Moody's prior-year comparative, both as guidance.
    """
    from ptm.asof import as_of_date

    current = as_of_date().year
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", sentence)]
    if not years:
        return False
    # Stale only when EVERY year named is in the past; a sentence comparing
    # last year to guidance for this one is still about this one.
    return all(y < current for y in years)


def parse_eps_guidance(text: str) -> dict | None:
    """Pull a full-year EPS guidance range out of an earnings release.

    Returns {low, high, midpoint, quote} or None. Conservative by design: a
    sentence must mention guidance AND earnings per share AND carry a dollar
    figure in a per-share range before it is trusted.
    """
    if not text:
        return None
    flat = re.sub(r"\s+", " ", text)
    # Earnings releases are bulleted, and the bullet glyphs survive extraction
    # (often mangled to U+FFFD). Splitting on sentence punctuation alone glued a
    # guidance clause to the results bullet that followed it, so the
    # "reported results" veto fired on the neighbour's wording and threw the
    # guidance away - SEZL's FY2026 raise was lost to a trailing "GMV grew 37.9%".
    flat = re.sub(r"[•‣▪●·�]+", ". ", flat)
    for sentence in re.split(r"(?<=[.;])\s+", flat):
        if len(sentence) > 600:
            continue
        if not (GUIDANCE_CUES.search(sentence) and EPS_CUES.search(sentence)):
            continue
        if not FULL_YEAR_CUES.search(sentence):
            continue
        if REPORTED_CUES.search(sentence):
            continue
        if re.search(r"per share.{0,40}(dividend|distribution)", sentence, re.I):
            continue
        # Measured on 195 candidates, the first working version of this parser
        # was right about 3 times in 9. The four failures each have a signature:
        # NOT a blanket veto on scale words: a real guidance sentence often
        # gives revenue and EPS together ("net sales down 4.5% to down 2.5%,
        # earnings per share of $3.00 to $3.25"). Only the figure actually
        # matched matters, so the check moved to _is_per_share below.
        if re.search(r"(current guidance|prior guidance)\s+(current|prior|Q[1-4]|full)", sentence, re.I):
            continue  # ATI: matched a guidance-comparison TABLE header
        if _mentions_stale_year(sentence):
            continue  # CDNS "fiscal 2024", MCO "FY 2022" - history, not guidance
        if re.search(r"\bGAAP\b(?!\s*[/-]?\s*non)", sentence) and re.search(r"non-?GAAP", sentence, re.I):
            continue  # EPAM/ILMN: release quotes BOTH bases; consensus is adjusted
        match = RANGE_RE.search(sentence)
        if match and _is_per_share(sentence, match):
            low, high = float(match.group(1)), float(match.group(2))
            if low <= high <= MAX_PLAUSIBLE_EPS:
                return {
                    "low": low,
                    "high": high,
                    "midpoint": (low + high) / 2,
                    "quote": sentence.strip()[:300],
                }
            continue
        single = SINGLE_RE.search(sentence)
        if single and _is_per_share(sentence, single):
            value = float(single.group(1))
            if 0 < value <= MAX_PLAUSIBLE_EPS:
                return {
                    "low": value,
                    "high": value,
                    "midpoint": value,
                    "quote": sentence.strip()[:300],
                }
    return None


def guidance_eps(ticker: str, max_chars: int = 12000) -> dict | None:
    """Company-issued EPS guidance from the most recent earnings exhibit public
    on the run date. None when the release carries no clean full-year range.

    Remember the basis mismatch documented above: what comes back is normally
    ADJUSTED EPS and must not be mixed with GAAP trailing figures.
    """
    try:
        text = latest_earnings_exhibit(ticker, max_chars=max_chars)
    except Exception:
        return None
    return parse_eps_guidance(text)
