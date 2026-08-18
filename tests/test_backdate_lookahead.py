"""Guards against future data leaking into a backdated run."""

from datetime import date

import pandas as pd

from ptm.asof import set_as_of
from pathlib import Path

from ptm.backdate import close_on
from ptm.fundamentals import source_warnings
from ptm.ingest import edgar
from ptm.ingest.ism import _fixture_is_stale_safe, _month_slugs
from ptm.pipeline import _bound_prices

FACTS = {
    "facts": {
        "us-gaap": {
            "EarningsPerShareDiluted": {
                "units": {
                    "USD/shares": [
                        # Q1 filed in time
                        {"start": "2026-01-01", "end": "2026-03-31", "val": 1.0, "filed": "2026-05-05", "form": "10-Q"},
                        # Q2 filed AFTER a 2026-06-20 run date
                        {"start": "2026-04-01", "end": "2026-06-30", "val": 9.9, "filed": "2026-08-05", "form": "10-Q"},
                    ]
                }
            }
        }
    }
}


def test_xbrl_facts_filed_after_the_run_date_are_invisible():
    series = FACTS["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"]
    set_as_of("2026-06-20")
    try:
        visible = edgar._visible_facts(series)
        assert [row["val"] for row in visible] == [1.0]
    finally:
        set_as_of(None)
    # Live run sees everything.
    assert len(edgar._visible_facts(series)) == 2


def test_latest_fact_ignores_a_period_that_had_not_been_filed_yet():
    set_as_of("2026-06-20")
    try:
        # The Q2 period ENDED before the run date but was not filed until August.
        assert edgar._latest_fact(FACTS, "us-gaap", "EarningsPerShareDiluted") == 1.0
    finally:
        set_as_of(None)
    assert edgar._latest_fact(FACTS, "us-gaap", "EarningsPerShareDiluted") == 9.9


def test_edgar_cache_paths_are_split_by_vintage():
    assert edgar._asof_suffix() == ""
    set_as_of("2026-06-20")
    try:
        assert edgar._asof_suffix() == "_2026-06-20"
    finally:
        set_as_of(None)


def test_submission_rows_after_the_run_date_are_dropped():
    recent = {
        "form": ["10-Q", "10-Q", "10-K"],
        "accessionNumber": ["a", "b", "c"],
        "filingDate": ["2026-08-05", "2026-05-05", "2026-02-04"],
    }
    set_as_of("2026-06-20")
    try:
        rows = edgar._visible_rows(recent, "form", "accessionNumber")
        assert [r[1] for r in rows] == ["b", "c"]
    finally:
        set_as_of(None)


def test_prices_after_the_run_date_are_dropped():
    frame = pd.DataFrame(
        {
            "date": ["2026-06-18", "2026-06-19", "2026-06-22", "2026-08-14"],
            "close": [10.0, 11.0, 12.0, 20.0],
            "ticker": ["A"] * 4,
        }
    )
    set_as_of("2026-06-20")
    try:
        bounded = _bound_prices(frame)
        assert list(bounded["date"]) == ["2026-06-18", "2026-06-19"]
        assert close_on(bounded, "A", date(2026, 6, 20)) == 11.0
    finally:
        set_as_of(None)
    # Live run keeps every bar.
    assert len(_bound_prices(frame)) == 4


def test_ism_months_follow_the_run_date():
    set_as_of("2026-06-20")
    try:
        assert _month_slugs()[0] == "may"
    finally:
        set_as_of(None)


def test_newer_ism_fixture_is_refused_as_lookahead():
    set_as_of("2026-06-20")
    try:
        # The bundled fixture is a July print; a June run must not see it.
        assert _fixture_is_stale_safe("July 2026") is False
        # An older print is stale but honest.
        assert _fixture_is_stale_safe("April 2026") is True
    finally:
        set_as_of(None)


def test_ism_fixture_allowed_when_it_matches_the_run_date():
    set_as_of("2026-08-18")
    try:
        assert _fixture_is_stale_safe("July 2026") is True
    finally:
        set_as_of(None)


def test_no_vendor_fundamentals_anywhere():
    """yfinance supplies prices and nothing else, on every run."""
    import ptm.ingest.yfinance_data as yfd

    for banned in ("fetch_fundamentals", "_merge_fundamentals_csv"):
        assert not hasattr(yfd, banned), f"{banned} would reintroduce vendor fundamentals"
    source = Path(yfd.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]  # skip the module docstring
    for token in ("stock.info", ".info or", "forwardEps", "trailingEps", "marketCap",
                  "targetMeanPrice", "recommendationMean", ".calendar", "stock.news"):
        assert token not in body, f"{token} is a fundamental and must not come from Yahoo"
    # Prices are the one thing it may still fetch.
    assert "history(" in body and "yf.download" in body


def test_backdated_run_declares_its_substitutions():
    frame = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "forward_eps": [1.0, 2.0],
            "price": [10.0, 20.0],
            "forward_source": ["management_guidance", "extrapolated"],
        }
    )
    warnings = source_warnings(frame)
    joined = " ".join(warnings)
    assert "not analyst consensus" in joined
    # Trailing P/E is exact and must be called out as such, not lumped in.
    assert "Trailing P/E is exact" in joined
    # The mix of forward-EPS sources is reported, never hidden.
    assert "1 from company guidance" in joined
    assert "1 extrapolated" in joined

    set_as_of("2026-07-20")
    try:
        backdated = " ".join(source_warnings(frame))
    finally:
        set_as_of(None)
    assert "survivorship" in backdated
    assert "projected from filing cadence" in backdated


def test_fundamentals_are_built_from_edgar_on_every_run(monkeypatch, isolate_roots):
    """Live and backdated runs take the same EDGAR path; neither touches Yahoo."""
    from ptm import pipeline

    seen = []
    monkeypatch.setattr(
        pipeline,
        "build_fundamentals",
        lambda universe, force=False: seen.append("edgar") or pd.DataFrame({"ticker": ["A"]}),
    )
    universe = pd.DataFrame({"ticker": ["A"], "name": ["A"], "sector": ["Industrials"]})

    pipeline._ensure_fundamentals(universe)
    set_as_of("2026-07-20")
    try:
        pipeline._ensure_fundamentals(universe)
    finally:
        set_as_of(None)
    assert seen == ["edgar", "edgar"]


def test_edgar_row_prices_off_the_run_date_close(monkeypatch, isolate_roots):
    from ptm.fundamentals import row_for

    monkeypatch.setattr(
        "ptm.ingest.edgar.company_fundamentals",
        lambda ticker, with_guidance=True: {
            "shares": 1_000_000.0,
            "eps_ttm": 2.0,
            "eps_prior_ttm": 1.6,
            "eps_basis": "4 quarterly filings",
            "report_dates": ["2026-05-05", "2026-02-04", "2025-11-05"],
            "guidance": None,
        },
    )
    prices = pd.DataFrame(
        {
            "date": ["2026-06-19", "2026-06-22", "2026-08-14"],
            "close": [50.0, 60.0, 99.0],
            "ticker": ["A"] * 3,
        }
    )
    row = row_for("A", "A", "Industrials", "Machinery", prices, date(2026, 6, 20))
    assert row["price"] == 50.0                  # the run date's close, not the latest
    assert row["market_cap"] == 50_000_000.0     # EDGAR shares x that close
    assert row["trailing_pe"] == 25.0            # exact
    assert row["trailing_pe_exact"] is True
    assert row["forward_source"] == "extrapolated"
    assert row["source"] == "edgar"
    assert row["earnings_date"] > "2026-06-20"


def test_guidance_beats_extrapolation_for_forward_eps(monkeypatch, isolate_roots):
    from ptm.fundamentals import row_for

    monkeypatch.setattr(
        "ptm.ingest.edgar.company_fundamentals",
        lambda ticker, with_guidance=True: {
            "shares": 1_000_000.0,
            "eps_ttm": 2.0,
            "eps_prior_ttm": 1.6,
            "eps_basis": "4 quarterly filings",
            "report_dates": ["2026-05-05"],
            "guidance": {"low": 2.4, "high": 2.6, "midpoint": 2.5, "quote": "we expect EPS of $2.40 to $2.60"},
        },
    )
    prices = pd.DataFrame({"date": ["2026-06-19"], "close": [50.0], "ticker": ["A"]})
    row = row_for("A", "A", "Industrials", "Machinery", prices, date(2026, 6, 20))
    assert row["forward_eps"] == 2.5
    assert row["forward_source"] == "management_guidance"
    assert "company guidance" in row["forward_basis"]
    assert row["earnings_growth"] == 0.25


def test_company_facts_reuses_the_prebuilt_extract(monkeypatch, isolate_roots):
    """One idea must not re-download a multi-MB companyfacts document that the
    fundamentals build already distilled."""
    from ptm.config import data_dir
    from ptm.ingest import edgar as e
    from ptm.io import write_json

    monkeypatch.setattr(e, "ticker_map", lambda: {"AAA": "0000000001"})

    def boom(*a, **k):
        raise AssertionError("companyfacts was re-downloaded")

    monkeypatch.setattr(e.requests, "get", boom)
    write_json(
        data_dir("raw", "edgar", "AAA_fundamentals.json"),
        {"ticker": "AAA", "revenue": 100.0, "net_income": 10.0, "ebit": 20.0,
         "cash": 5.0, "debt": 30.0, "assets": 200.0, "equity": 80.0, "interest": 2.0},
    )
    facts = e.company_facts("AAA")
    assert facts["revenue"] == 100.0
    assert facts["ebit"] == 20.0
    assert facts["interest"] == 2.0


def test_earnings_exhibit_picks_the_newest_8k_and_unpacks_cleanly(monkeypatch, isolate_roots):
    """Regression: adding filingDate to the row tuple broke the unpacking, and
    the exhibit fetch failed silently for every ticker behind a caught except."""
    from ptm.ingest import edgar as e

    monkeypatch.setattr(e, "ticker_map", lambda: {"AAA": "0000000001"})
    recent = {
        "form": ["8-K", "8-K", "10-Q"],
        "accessionNumber": ["old", "new", "q"],
        "primaryDocument": ["o.htm", "n.htm", "q.htm"],
        "items": ["2.02", "2.02", ""],
        "filingDate": ["2020-11-05", "2026-07-28", "2026-08-01"],
    }
    picked = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            # Serves both the submissions feed and the per-filing index.
            return {
                "filings": {"recent": recent},
                "directory": {"item": [{"name": "ex991.htm"}]},
            }

    monkeypatch.setattr(e.requests, "get", lambda url, **k: FakeResponse())

    def fake_fetch(cik, acc, name, timeout=30):
        picked.append(acc)
        return "<html>Exhibit 99.1 Earnings Release net income earnings per share of $1.00</html>"

    monkeypatch.setattr(e, "_fetch_doc", fake_fetch)
    monkeypatch.setattr(e, "is_cover_page", lambda text: False)
    monkeypatch.setattr(e, "is_exhibit99_name", lambda name: True)
    monkeypatch.setattr(e, "_strip_html", lambda html: "Exhibit 99.1 Earnings Release " + "x" * 300)

    out = e.latest_earnings_exhibit("AAA")
    assert out, "exhibit must be returned, not swallowed by an unpacking error"
    # The 2026 release must win over the 2020 one.
    assert picked and picked[0] == "new"
