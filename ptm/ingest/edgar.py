"""SEC EDGAR companyfacts + recent 10-K/10-Q text."""

from __future__ import annotations

import re
import time
import warnings
from functools import lru_cache

import requests
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning

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


def _headers() -> dict:
    return {
        "User-Agent": env().sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/html, */*",
    }


@lru_cache
def ticker_map() -> dict[str, str]:
    cache = data_dir("curated", "sec_tickers.json")
    if cache.exists():
        return {k: str(v) for k, v in read_json(cache).items()}
    for url in TICKERS_URLS:
        try:
            response = requests.get(url, headers=_headers(), timeout=30)
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


def _latest_fact(facts: dict, taxonomy: str, tag: str) -> float | None:
    node = facts.get("facts", {}).get(taxonomy, {}).get(tag, {})
    units = node.get("units", {})
    series = units.get("USD") or units.get("USD/shares") or next(iter(units.values()), None)
    if not series:
        return None
    annual = [row for row in series if row.get("form") in {"10-K", "10-Q"} and row.get("val") is not None]
    if not annual:
        return None
    annual.sort(key=lambda row: row.get("end") or "", reverse=True)
    return float(annual[0]["val"])


def company_facts(ticker: str) -> dict:
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return {"ticker": ticker, "error": "no CIK"}
    cache = data_dir("raw", "edgar", f"{ticker}_facts.json")
    if cache.exists():
        return read_json(cache)
    url = FACTS_URL.format(cik=cik)
    response = requests.get(url, headers=_headers(), timeout=45)
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
    time.sleep(0.15)
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
    cache = data_dir("raw", "edgar", f"{ticker}_filing.txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    return ""


def _cache_sections_usable(payload: dict) -> bool:
    business = str(payload.get("business") or "")
    mda = str(payload.get("mda") or "")
    return len(business.strip()) >= 40 or len(mda.strip()) >= 200


def filing_sections(ticker: str, max_chars: int = 4000) -> dict[str, str]:
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return {"business": "", "mda": ""}
    cache = data_dir("raw", "edgar", f"{ticker}_sections.json")
    if cache.exists():
        cached = read_json(cache)
        if _cache_sections_usable(cached):
            return cached
    url = SUBMISSIONS_URL.format(cik=cik)
    response = requests.get(url, headers=_headers(), timeout=45)
    if response.status_code >= 400:
        return {"business": "", "mda": ""}
    recent = response.json().get("filings", {}).get("recent", {})
    forms_list = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])
    pairs = list(zip(forms_list, accs, primaries))
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
            raw = data_dir("raw", "edgar", f"{ticker}_filing.txt")
            raw.write_text(last_text[: max_chars * 4], encoding="utf-8", errors="ignore")
    return extracted


def latest_earnings_exhibit(ticker: str, max_chars: int = 5000) -> str:
    cik = ticker_map().get(ticker.upper().replace(".", "-"))
    if not cik:
        return ""
    cache = data_dir("raw", "edgar", f"{ticker}_ex99.txt")
    if cache.exists():
        cached = cache.read_text(encoding="utf-8", errors="ignore")
        if cached and not is_cover_page(cached):
            return cached[:max_chars]
    url = SUBMISSIONS_URL.format(cik=cik)
    response = requests.get(url, headers=_headers(), timeout=45)
    if response.status_code >= 400:
        return ""
    recent = response.json().get("filings", {}).get("recent", {})
    forms_list = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])
    items_list = recent.get("items") or [""] * len(forms_list)
    indexed = list(zip(forms_list, accs, primaries, items_list))
    indexed.sort(key=lambda row: (0 if "2.02" in str(row[3]) else 1))
    for form, acc, _primary, _items in indexed:
        if not str(form).startswith("8-K"):
            continue
        acc_nodash = acc.replace("-", "")
        index_url = INDEX_JSON.format(cik=int(cik), acc=acc_nodash)
        try:
            index = requests.get(index_url, headers=_headers(), timeout=20)
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
