"""Guards against future data leaking into a backdated run."""

from datetime import date

import pandas as pd
import pytest

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

    # No consensus available: exercise the EDGAR-only fallback.
    monkeypatch.setattr("ptm.fundamentals.consensus_eps", lambda ticker: None)
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

    monkeypatch.setattr("ptm.fundamentals.consensus_eps", lambda ticker: None)
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


def test_live_extract_cache_expires_but_backdated_does_not(monkeypatch, isolate_roots):
    """A cached XBRL extract is keyed by ticker alone. On a live run it must age
    out, or a company filing a fresh 10-Q is invisible until someone clears the
    cache by hand. A backdated extract is pinned to its vintage and cannot stale."""
    import os
    import time as _time

    from ptm.config import data_dir
    from ptm.ingest import edgar as e
    from ptm.io import write_json

    path = data_dir("raw", "edgar", "AAA_fundamentals.json")
    write_json(path, {"ticker": "AAA"})

    assert e._cache_fresh(path) is True

    # Backdate it beyond the window.
    stale = _time.time() - (e.extract_max_age_days() + 1) * 86400
    os.utime(path, (stale, stale))
    assert e._cache_fresh(path) is False, "a stale live extract must be refetched"

    set_as_of("2026-06-20")
    try:
        # Same file, but a backdated run pins its own vintage.
        pinned = data_dir("raw", "edgar", "AAA_fundamentals_2026-06-20.json")
        write_json(pinned, {"ticker": "AAA"})
        os.utime(pinned, (stale, stale))
        assert e._cache_fresh(pinned) is True
    finally:
        set_as_of(None)


def test_consensus_is_refused_on_a_backdated_run(monkeypatch, isolate_roots):
    """Today's estimates carry no history. Using them to screen a past date is
    exactly the lookahead the rest of the pipeline exists to prevent."""
    from ptm.ingest import estimates

    called = []
    monkeypatch.setattr("yfinance.Ticker", lambda t: called.append(t))

    set_as_of("2026-06-20")
    try:
        assert estimates.consensus_eps("AAPL") is None
    finally:
        set_as_of(None)
    assert called == [], "a backdated run must not even ask for consensus"

    warnings = estimates.warn_if_thin(100, 0)
    set_as_of("2026-06-20")
    try:
        warnings = estimates.warn_if_thin(100, 0)
    finally:
        set_as_of(None)
    assert any("BACKDATED RUN" in w and "lookahead" in w for w in warnings)


def test_consensus_gives_independent_growth_rates(monkeypatch, isolate_roots):
    """The whole point: eg1 and eg2 stop being the same number."""
    from ptm.fundamentals import row_for

    monkeypatch.setattr(
        "ptm.fundamentals.consensus_eps",
        lambda ticker: {
            "eps1": 8.81, "eps2": 9.53, "prior_eps": 7.46,
            "eg1": 0.1803, "eg2": 0.0826, "analysts": 38, "basis": "test",
        },
    )
    monkeypatch.setattr(
        "ptm.ingest.edgar.company_fundamentals",
        lambda ticker, with_guidance=True: {
            "shares": 1_000_000.0, "eps_ttm": 7.0, "eps_prior_ttm": 6.0,
            "eps_basis": "4 quarterly filings", "report_dates": ["2026-05-05"], "guidance": None,
        },
    )
    prices = pd.DataFrame({"date": ["2026-08-18"], "close": [100.0], "ticker": ["AAPL"]})
    row = row_for("AAPL", "Apple", "Information Technology", "Hardware", prices, date(2026, 8, 18))

    assert row["forward_source"] == "analyst_consensus"
    assert row["forward_eps"] == 8.81 and row["forward_eps2"] == 9.53
    assert row["eg1"] != row["eg2"], "eg1 and eg2 must be independent"
    assert row["eg1"] == 0.1803 and row["eg2"] == 0.0826
    # Trailing P/E stays EDGAR GAAP and exact, not recomputed on adjusted EPS.
    assert row["trailing_eps"] == 7.0
    assert row["trailing_pe"] == pytest.approx(100.0 / 7.0)
    assert row["trailing_pe_exact"] is True


def test_thin_coverage_falls_back_rather_than_trusting_two_analysts(monkeypatch, isolate_roots):
    from ptm.ingest import estimates

    class FakeFrame:
        empty = False

        @staticmethod
        def loc_get(period, column):
            return None

        class _Loc:
            def __getitem__(self, key):
                period, column = key
                data = {
                    ("0y", "avg"): 5.0, ("+1y", "avg"): 6.0, ("0y", "yearAgoEps"): 4.0,
                    ("0y", "numberOfAnalysts"): 1, ("0y", "growth"): 0.25, ("+1y", "growth"): 0.2,
                }
                return data.get((period, column))

        loc = _Loc()

    monkeypatch.setattr("yfinance.Ticker", lambda t: type("T", (), {"earnings_estimate": FakeFrame()})())
    assert estimates.consensus_eps("THIN") is None, "1 analyst is not a consensus"


def test_transcripts_are_off_without_a_key(monkeypatch, isolate_roots):
    """Inert until configured: no key means no calls and no pack section."""
    from ptm.ingest import transcripts

    monkeypatch.delenv("TRANSCRIPT_API_KEY", raising=False)
    assert transcripts.enabled() is False
    assert transcripts.fetch("AAPL") == []
    assert transcripts.pack_section("AAPL") == ""


def test_backdated_runs_drop_later_and_undated_calls(monkeypatch, isolate_roots):
    """A call held after the run date is lookahead; an undated one cannot be
    shown to be in the past, so both are refused."""
    from ptm.ingest import transcripts

    monkeypatch.setattr(transcripts, "enabled", lambda: True)
    monkeypatch.setattr(transcripts, "api_key", lambda: "k")
    monkeypatch.setattr(transcripts, "provider", lambda: "fake")
    monkeypatch.setitem(
        transcripts.PROVIDERS,
        "fake",
        lambda ticker, key, limit: [
            {"date": "2026-08-05", "quarter": 2, "year": 2026, "text": "revenue grew 9%"},
            {"date": "2026-06-01", "quarter": 1, "year": 2026, "text": "margins expanded 200 bps"},
            {"date": None, "quarter": None, "year": None, "text": "undated call"},
        ],
    )
    set_as_of("2026-07-01")
    try:
        rows = transcripts.fetch("AAA")
    finally:
        set_as_of(None)
    dates = [r["date"] for r in rows]
    assert dates == ["2026-06-01"], f"kept {dates}"


def test_densest_window_prefers_period_over_period_language():
    """Prepared remarks are rarely at the top; the operator preamble is."""
    from ptm.ingest.transcripts import densest_window

    text = (
        "Operator: thank you for standing by. " * 40
        + "Revenue grew 9% and margins expanded 200 basis points while EPS rose 15%. "
        + "Safe harbour statement follows. " * 40
    )
    window = densest_window(text, 400)
    # The invariant is that the window finds the numbers, not that it excludes
    # all surrounding prose - a 400-char window around a 75-char sentence will
    # always carry neighbours. What matters is that it beats taking the head.
    assert "grew 9%" in window and "200 basis points" in window
    assert "grew 9%" not in text[:400], "the head is the wrong passage, which is the point"


def test_expectations_are_refused_on_a_backdated_run():
    """Options chains, revisions and surprise tables all describe TODAY and have
    no vintage. Serving them to a historical run is the exact lookahead the rest
    of this module exists to prevent."""
    from ptm.ingest.expectations import build_expectations, expectations

    set_as_of("2026-06-15")
    try:
        assert expectations("AAPL", "2026-07-01") is None
        assert build_expectations(["AAPL"]) == {}
    finally:
        set_as_of(None)


def test_expectations_module_guards_before_any_network_call():
    """The guard must sit above the fetch, not inside it — a network call made
    and then discarded still costs a rate limit and still risks being cached."""
    import ptm.ingest.expectations as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]
    guard = body.index("if is_backdated():\n        return None")
    fetch = body.index('payload = {\n        "ticker": ticker')
    assert guard < fetch, "the backdating guard must precede the fetch"
