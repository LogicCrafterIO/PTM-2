from datetime import datetime, timezone
from pathlib import Path

import pytest

from ptm.ingest.ism import _login_walled, _month_slugs, _urls, fetch_ism_html, parse_ism_report, scrape_ism

FIXTURES = Path(__file__).parent / "fixtures"


def test_login_wall_detection():
    assert _login_walled("https://ecommerce.ismworld.org/SSO/Login?foo=1")
    assert not _login_walled("https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/july/")


def test_urls_try_prior_month_first():
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    assert _month_slugs(now) == ["july", "june", "may", "april"]
    urls = _urls(now)
    kinds = [k for k, _ in urls]
    assert kinds.count("pmi") >= 2
    first_pmi = next(url for kind, url in urls if kind == "pmi")
    # a live run probes the month the calendar cannot yet vouch for; it falls
    # back to the both-out calendar month when that page is not live
    assert first_pmi.endswith("/pmi/august/")
    assert [u for k, u in urls if k == "pmi"][1].endswith("/pmi/july/")
    jan = datetime(2026, 1, 10, tzinfo=timezone.utc)
    assert _month_slugs(jan)[0] == "december"


def test_urls_respect_the_two_release_days():
    """Manufacturing goes live on business day 1 of M+1, Services on business
    day 3 — September 2026 is the live case: the 1st is a Tuesday, so August's
    PMI page is out on the 1st and Services' only on the 3rd."""
    sep1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    pmi_first = next(u for k, u in _urls(sep1, allow_probe=True) if k == "pmi")
    svc_first = next(u for k, u in _urls(sep1, allow_probe=True) if k == "services")
    assert pmi_first.endswith("/pmi/august/")
    assert svc_first.endswith("/services/july/")  # business day 1 < 3
    sep3 = datetime(2026, 9, 3, tzinfo=timezone.utc)
    svc3 = next(u for k, u in _urls(sep3, allow_probe=True) if k == "services")
    assert svc3.endswith("/services/august/")


def test_urls_never_probe_newer_month_backdated():
    from ptm.asof import real_today, set_as_of

    set_as_of("2026-09-02")  # strictly before real_today, so is_backdated() is True
    try:
        urls = _urls()
        assert next(u for k, u in urls if k == "pmi").endswith("/pmi/july/")
        assert next(u for k, u in urls if k == "services").endswith("/services/july/")
    finally:
        set_as_of(None)


def test_fetch_login_wall_raises(monkeypatch):
    calls = []

    def boom_curl(url: str) -> str:
        calls.append("curl")
        raise RuntimeError("ISM login wall")

    monkeypatch.setattr("ptm.ingest.ism._get_curl", boom_curl)
    with pytest.raises(RuntimeError, match="login wall"):
        fetch_ism_html("https://example.test/pmi")
    assert calls == ["curl"]


def test_fetch_rejects_empty_and_http(monkeypatch):
    def fake_curl(url: str) -> str:
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr("ptm.ingest.ism._get_curl", fake_curl)
    with pytest.raises(RuntimeError, match="HTTP 403"):
        fetch_ism_html("https://example.test")


def test_scrape_local_files_skips_fetch(monkeypatch):
    def fail(url: str) -> str:
        raise AssertionError("fetch should not run")

    monkeypatch.setattr("ptm.ingest.ism.fetch_ism_html", fail)
    payload = scrape_ism(
        pmi_html=FIXTURES / "ism_july_manufacturing.md",
        services_html=FIXTURES / "ism_july_services.md",
    )
    assert payload["pmi"] == 55.6
    assert payload["nmi"] == 54.1
    assert payload["errors"] == []


def test_scrape_falls_back_to_july_fixture(monkeypatch):
    monkeypatch.setattr("ptm.ingest.ism.fetch_ism_html", lambda url: (_ for _ in ()).throw(RuntimeError("ISM login wall")))
    payload = scrape_ism()
    assert payload["pmi"] == 55.6
    assert payload["nmi"] == 54.1
    assert any("fixture" in err.lower() for err in payload["errors"])


def test_html_min_fixture_parses_headline():
    html = (FIXTURES / "ism_html_min.html").read_text(encoding="utf-8")
    report = parse_ism_report(html, "pmi")
    assert report["headline"] == 55.6
    assert report["report_month"] and "July" in report["report_month"]
