"""Scrape and parse ISM Manufacturing / Services PMI monthly reports."""

from __future__ import annotations

import calendar
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from bs4 import BeautifulSoup

from ptm.config import ROOT, data_dir
from ptm.io import write_json
from ptm.log import log

BASE = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports"
HOME = "https://www.ismworld.org/"
# Cloudflare on ismworld.org empty-replies HTTP/2 (curl 52). HTTP/1.1 + Chrome
# impersonation + a homepage cookie warmup is what a real browser does.
CURL_TRIES = 3
HTTP_1_1 = "v1"  # curl_cffi: HTTP/1.1 (int 1 is HTTP/1.0; default is HTTP/2 → curl 52)

_session_lock = Lock()
_session = None
_warmed = False

COMPONENT_LABELS = [
    ("headline_mfg", r"Manufacturing PMI"),
    ("headline_svc", r"Services PMI"),
    ("new_orders", r"New Orders"),
    ("production", r"Production"),
    ("business_activity", r"Business Activity(?:/Production)?"),
    ("employment", r"Employment"),
    ("supplier_deliveries", r"Supplier Deliveries"),
    ("inventories", r"Inventories"),
    ("customer_inventories", r"Customers['’] Inventories"),
    ("prices", r"Prices"),
    ("backlog", r"Backlog of Orders"),
    ("exports", r"New Export Orders"),
    ("imports", r"Imports"),
    ("inventory_sentiment", r"Inventory Sentiment"),
]


def _month_slugs(now: datetime | None = None) -> list[str]:
    """Latest *released* print is last calendar month (August URL is empty mid-August)."""
    now = now or datetime.now(timezone.utc)
    month = now.month - 1 or 12
    names: list[str] = []
    for _ in range(4):
        names.append(calendar.month_name[month].lower())
        month = month - 1 or 12
    return names


def _urls(now: datetime | None = None) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for month in _month_slugs(now):
        urls.append(("pmi", f"{BASE}/pmi/{month}/"))
        urls.append(("services", f"{BASE}/services/{month}/"))
    return urls


def _login_walled(url: str) -> bool:
    return "SSO/Login" in url or "ecommerce.ismworld.org" in url


def _new_session():
    from curl_cffi import requests as cffi_requests

    return cffi_requests.Session(impersonate="chrome131", http_version=HTTP_1_1)


def _sess():
    global _session
    if _session is None:
        _session = _new_session()
    return _session


def _reset_session() -> None:
    global _session, _warmed
    _session = _new_session()
    _warmed = False


def _warmup() -> None:
    global _warmed
    if _warmed:
        return
    try:
        response = _sess().get(HOME, timeout=30, allow_redirects=True)
        if response.status_code < 400 and (response.text or ""):
            _warmed = True
            return
        log(f"ism: homepage warmup HTTP {response.status_code}")
    except Exception as exc:
        log(f"ism: homepage warmup failed ({exc}); trying report URL anyway")


def _get_curl(url: str) -> str:
    with _session_lock:
        last: Exception | None = None
        for attempt in range(CURL_TRIES):
            # Homepage first only after a miss: a direct report GET often works on
            # HTTP/1.1, and www.ismworld.org/ itself is the flakier 52 target.
            if attempt > 0:
                _warmup()
            try:
                response = _sess().get(url, timeout=30, allow_redirects=True)
            except Exception as exc:
                last = exc
                log(f"ism curl retry {attempt + 1}/{CURL_TRIES}: {exc}")
                _reset_session()
                time.sleep(1.5 * (attempt + 1))
                continue
            final = str(getattr(response, "url", url))
            if _login_walled(final):
                last = RuntimeError("ISM login wall")
                _reset_session()
                time.sleep(0.8)
                continue
            if response.status_code >= 400:
                last = RuntimeError(f"HTTP {response.status_code}")
                time.sleep(1.5 * (attempt + 1))
                continue
            text = response.text or ""
            if len(text) < 800:
                last = RuntimeError("empty or stub ISM page")
                time.sleep(1.5 * (attempt + 1))
                continue
            return text
        raise last or RuntimeError("ISM fetch failed")


def fetch_ism_html(url: str) -> str:
    return _get_curl(url)


def _plain(html_or_text: str) -> str:
    if "<html" in html_or_text.lower() or "<div" in html_or_text.lower() or "<p" in html_or_text.lower():
        soup = BeautifulSoup(html_or_text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    else:
        text = html_or_text
    return text.replace("\u00a0", " ")


def _parse_registered(text: str, labels: tuple[str, ...]) -> float | None:
    blob = re.sub(r"\s+", " ", text)
    for label in labels:
        patterns = [
            rf"{label}\s*PMI[®\s]*registered\s+(\d{{2}}(?:\.\d)?)\s*percent",
            rf"{label}\s*PMI[®\s]*at\s+(\d{{2}}(?:\.\d)?)%",
            rf"{label}\s*PMI[®\s]*at\s+(\d{{2}}(?:\.\d)?)",
            rf"{label} PMI[^\d]{{0,40}}(\d{{2}}(?:\.\d)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, blob, flags=re.I)
            if match:
                value = float(match.group(1))
                if 20 <= value <= 80:
                    return value
    return None


def _index_value(blob: str, name: str) -> float | None:
    patterns = [
        rf"{name}\s*Index[^.{{]{{0,160}}?(?:registering|reading of|registered)\s+(\d{{2}}(?:\.\d)?)\s*percent",
        rf"{name}\s*Index\s+at\s+(\d{{2}}(?:\.\d)?)%",
        rf"\|\s*{name}[®\s/A-Za-z]*\|\s*(\d{{2}}(?:\.\d)?)\s*\|",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob, flags=re.I)
        if match:
            value = float(match.group(1))
            if 20 <= value <= 80:
                return value
    return None


def _glance_components(text: str, kind: str) -> dict[str, dict]:
    components: dict[str, dict] = {}
    blob = text
    table_re = re.compile(
        r"\|\s*(?P<name>[A-Za-z][^|®]*?)[®]?\s*\|\s*(?P<jul>\d{2}(?:\.\d)?)\s*\|\s*(?P<jun>\d{2}(?:\.\d)?)\s*\|\s*(?P<chg>[+\-−]?\d+(?:\.\d)?)",
    )
    label_map = {
        "manufacturing pmi": "headline",
        "services pmi": "headline",
        "new orders": "new_orders",
        "production": "production",
        "business activity": "business_activity",
        "business activity/production": "business_activity",
        "employment": "employment",
        "supplier deliveries": "supplier_deliveries",
        "inventories": "inventories",
        "customers' inventories": "customer_inventories",
        "customers’ inventories": "customer_inventories",
        "prices": "prices",
        "backlog of orders": "backlog",
        "new export orders": "exports",
        "imports": "imports",
        "inventory sentiment": "inventory_sentiment",
    }
    for match in table_re.finditer(text):
        raw = re.sub(r"\s+", " ", match.group("name")).strip().lower()
        key = label_map.get(raw)
        if not key:
            continue
        components[key] = {
            "value": float(match.group("jul")),
            "prior": float(match.group("jun")),
            "delta": float(match.group("chg").replace("−", "-")),
        }

    prose = re.sub(r"\s+", " ", blob)
    if "headline" not in components:
        labels = ("Manufacturing",) if kind == "pmi" else ("Services", "Non-Manufacturing", "NMI")
        headline = _parse_registered(prose, labels)
        if headline is not None:
            components["headline"] = {"value": headline, "prior": None, "delta": None}

    prose_names = [
        ("new_orders", "New Orders"),
        ("production", "Production"),
        ("business_activity", "Business Activity"),
        ("employment", "Employment"),
        ("supplier_deliveries", "Supplier Deliveries"),
        ("inventories", "Inventories"),
        ("customer_inventories", r"Customers['’] Inventories"),
        ("prices", "Prices"),
        ("backlog", "Backlog of Orders"),
        ("exports", "New Export Orders"),
        ("imports", "Imports"),
    ]
    for key, name in prose_names:
        if key in components:
            continue
        value = _index_value(prose, name)
        if value is not None:
            components[key] = {"value": value, "prior": None, "delta": None}

    trend_re = re.compile(
        r"\|\s*(?P<name>[A-Za-z][^|®]*?)[®]?\s*\|\s*(?P<jul>\d{2}(?:\.\d)?)\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*(?P<trend>\d+)\s*\|"
    )
    for match in trend_re.finditer(text):
        raw = re.sub(r"\s+", " ", match.group("name")).strip().lower()
        key = label_map.get(raw)
        if key and key in components:
            components[key]["trend_months"] = int(match.group("trend"))
    return components


def _split_industries(blob: str) -> list[str]:
    blob = blob.replace("\n", " ")
    blob = re.sub(r"\s+", " ", blob).strip(" .")
    blob = re.sub(r"\band\s+", "; ", blob)
    names = []
    for part in blob.split(";"):
        name = part.strip(" :.")
        name = re.sub(r"^(?:the\s+)?(?:only\s+)?industr(?:y|ies)\s+", "", name, flags=re.I)
        if 3 < len(name) < 90 and not name.lower().startswith("the "):
            names.append(name)
        elif 3 < len(name) < 90:
            cleaned = re.sub(r"^the\s+", "", name, flags=re.I)
            if cleaned:
                names.append(cleaned)
    # drop leftover clause fragments
    skip = {"listed in order", "in order", "in the following order"}
    return [n for n in names if n.lower() not in skip and "reporting" not in n.lower()]


def _industry_clause(text: str, growth_hint: str, contract_hint: str | None = None) -> dict:
    growth: list[str] = []
    contraction: list[str] = []
    grow_match = re.search(
        rf"{growth_hint}[:\s]+(.+?)(?:\.|$)",
        text,
        flags=re.I | re.S,
    )
    if grow_match:
        growth = _split_industries(grow_match.group(1))
    if contract_hint:
        con_match = re.search(rf"{contract_hint}[:\s]+(.+?)(?:\.|$)", text, flags=re.I | re.S)
        if con_match:
            contraction = _split_industries(con_match.group(1))
    if not contraction:
        only = re.search(
            r"only industry in contraction was\s+([^.]{3,80})\.",
            text,
            flags=re.I,
        )
        if only:
            contraction = _split_industries(only.group(1))
    return {"growth": growth, "contraction": contraction}


def _parse_industry_lists(text: str) -> dict:
    headline = _industry_clause(
        text,
        r"industries reporting growth[^.]*?(?:listed in order|in order)[^.]*?are",
        r"industries reporting (?:a )?contraction[^.]*?(?:are|were)",
    )
    if not headline["growth"]:
        headline = _industry_clause(
            text,
            r"services industries reporting growth[^.]*?are",
            r"industries reporting a contraction[^.]*?are",
        )
    new_orders = _industry_clause(
        text,
        r"industries (?:that )?reported growth in new orders[^.]*?are",
        r"industries reporting a decline in new orders[^.]*?are",
    )
    return {"headline": headline, "new_orders": new_orders}


def _parse_comments(text: str) -> list[dict]:
    block = text
    start = re.search(r"WHAT RESPONDENTS ARE SAYING", text, flags=re.I)
    if start:
        rest = text[start.end() :]
        end = re.search(
            r"MANUFACTURING AT A GLANCE|ISM® SERVICES SURVEY|COMMODITIES REPORTED",
            rest,
            flags=re.I,
        )
        block = rest[: end.start()] if end else rest[:8000]
    comments = []
    pattern = re.compile(
        r"[“\"](.+?)[”\"]\s*\[([^\]]+)\]",
        flags=re.S,
    )
    for match in pattern.finditer(block):
        quote = re.sub(r"\s+", " ", match.group(1)).strip()
        industry = match.group(2).strip()
        if quote and industry:
            comments.append({"industry": industry, "quote": quote})
    return comments


def parse_ism_report(html_or_text: str, kind: str = "pmi") -> dict:
    text = _plain(html_or_text)
    components = _glance_components(text, kind)
    lists = _parse_industry_lists(text)
    comments = _parse_comments(text)
    headline = (components.get("headline") or {}).get("value")
    if headline is None:
        labels = ("Manufacturing",) if kind == "pmi" else ("Services", "Non-Manufacturing", "NMI")
        headline = _parse_registered(text, labels)
        if headline is not None:
            components["headline"] = {"value": headline, "prior": None, "delta": None}
    month = None
    month_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        text,
        flags=re.I,
    )
    if month_match:
        month = f"{month_match.group(1)} {month_match.group(2)}"
    return {
        "kind": "manufacturing" if kind == "pmi" else "services",
        "report_month": month,
        "headline": headline,
        "components": components,
        "industries": lists["headline"],
        "new_orders_industries": lists["new_orders"],
        "comments": comments,
    }


def scrape_ism(
    pmi_html: str | Path | None = None,
    services_html: str | Path | None = None,
) -> dict:
    errors: list[str] = []
    used: dict[str, str] = {}
    manufacturing = None
    services = None

    def _load(value: str | Path | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
        return str(value)

    local_pmi = _load(pmi_html)
    local_svc = _load(services_html)
    if local_pmi:
        log(f"ism: using local PMI file {pmi_html}")
        manufacturing = parse_ism_report(local_pmi, "pmi")
        used["pmi"] = str(pmi_html)
    if local_svc:
        log(f"ism: using local services file {services_html}")
        services = parse_ism_report(local_svc, "services")
        used["services"] = str(services_html)

    if manufacturing is None or services is None:
        log("ism: curling ismworld.org (HTTP/1.1 + homepage warmup; July fixture if still blocked)")
        for kind, url in _urls():
            if kind == "pmi" and manufacturing is not None:
                continue
            if kind == "services" and services is not None:
                continue
            log(f"ism curl {kind} {url}")
            try:
                html = fetch_ism_html(url)
                time.sleep(0.8)
                raw_dir = data_dir("raw", "ism")
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"{kind}.html").write_text(html, encoding="utf-8", errors="ignore")
                report = parse_ism_report(html, kind)
            except Exception as exc:
                log(f"ism curl FAIL {url}: {exc}")
                errors.append(f"{url}: {exc}")
                time.sleep(0.8)
                continue
            if not report.get("headline"):
                log(f"ism parse empty headline {url}")
                errors.append(f"{url}: parsed no headline")
                continue
            log(f"ism got {kind} headline={report.get('headline')}")
            if kind == "pmi":
                manufacturing = report
                used["pmi"] = url
            else:
                services = report
                used["services"] = url

    fixtures = ROOT / "tests" / "fixtures"
    if manufacturing is None:
        path = fixtures / "ism_july_manufacturing.md"
        if path.exists():
            manufacturing = parse_ism_report(path.read_text(encoding="utf-8"), "pmi")
            used["pmi"] = str(path)
            errors.append("live manufacturing fetch failed; used bundled July fixture")
            log("ism: using bundled July manufacturing fixture")
    if services is None:
        path = fixtures / "ism_july_services.md"
        if path.exists():
            services = parse_ism_report(path.read_text(encoding="utf-8"), "services")
            used["services"] = str(path)
            errors.append("live services fetch failed; used bundled July fixture")
            log("ism: using bundled July services fixture")

    if manufacturing is None and services is None:
        existing_path = data_dir("curated", "ism.json")
        if existing_path.exists():
            from ptm.io import read_json

            existing = read_json(existing_path)
            if existing.get("pmi") or existing.get("nmi"):
                existing["errors"] = list(existing.get("errors") or []) + errors
                return existing

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "pmi": (manufacturing or {}).get("headline"),
        "nmi": (services or {}).get("headline"),
        "manufacturing": manufacturing,
        "services": services,
        "source": "ismworld.org",
        "urls": used,
        "errors": errors,
    }
    write_json(data_dir("curated", "ism.json"), payload)
    log(f"ism done pmi={payload.get('pmi')} nmi={payload.get('nmi')} errors={len(errors)}")
    return payload
