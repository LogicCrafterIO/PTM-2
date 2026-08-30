from ptm.book import assemble_book
from ptm.config import data_dir, ideas_dir
from ptm.io import read_df, read_json, write_df
from ptm.llm import qualitative
from ptm.models import Candidate, IdeaState, MacroSnapshot, QualResult, Side, TradeIdea
from ptm.organize import BEYOND, bucket_names, sector_slug
from ptm.pipeline import generate_ideas, ingest, research_funnel
from tests.conftest import seed_pipeline_data


def test_skip_llm_marks_deferred_flag(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: False)
    result = qualitative(Candidate(ticker="X", side=Side.LONG), "excerpt")
    assert "llm_skipped" in result.red_flags
    assert isinstance(result, QualResult)


def test_skip_llm_is_not_a_quality_pass(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: False)
    result = qualitative(Candidate(ticker="X", side=Side.LONG), "excerpt")
    assert result.supports_outlier is not True


def test_offline_generate_ideas_writes_markdown_and_book(monkeypatch):
    seed_pipeline_data()
    monkeypatch.setattr("ptm.llm.llm_available", lambda: False)
    monkeypatch.setattr("ptm.pipeline.llm_available", lambda: False)
    ideas = generate_ideas(max_candidates=4, skip_llm=True)
    assert len(ideas) == 4
    day_dirs = list(ideas_dir().iterdir())
    assert day_dirs
    for idea in ideas:
        stem = f"{idea.candidate.side.value}_{idea.candidate.ticker}"
        # ideas/<day>/<Sector>/<earnings-bucket>/<side>_<ticker>.md
        md = next(ideas_dir().glob(f"*/*/*/{stem}.md"))
        assert md.parent.name in set(bucket_names()) | {BEYOND}
        assert md.parent.parent.name == sector_slug(idea.candidate.sector)
        text = md.read_text(encoding="utf-8")
        assert text.strip()
        assert not text.lstrip().startswith("{")
        assert md.with_suffix(".json").exists()
        assert idea.candidate.warnings is not None
    dumped = read_json(data_dir("curated", "ideas.json"))
    assert len(dumped) == 4
    ranking = read_json(data_dir("curated", "ranking.json"))
    assert ranking["rows"]
    assert any("why" in row and row["why"] for row in ranking["rows"])
    assert list(ideas_dir().glob("*/RANKING.md"))
    for row in dumped:
        from ptm.models import TradeIdea

        TradeIdea.model_validate(row)
    assert data_dir("curated", "book.json").exists()
    snap = MacroSnapshot.model_validate(read_json(data_dir("curated", "macro_snapshot.json")))
    book = assemble_book(ideas, snap.bias)
    idea_tickers = {i.candidate.ticker for i in ideas}
    book_tickers = {i.candidate.ticker for i in book.ideas}
    assert book_tickers <= idea_tickers
    templated = [i for i in ideas if i.state in {IdeaState.TEMPLATED, IdeaState.SIZED}]
    if templated:
        assert book.ideas


def test_broken_llm_json_still_writes_markdown(monkeypatch):
    seed_pipeline_data()

    def fake_pack(cand):
        return {"text": "BUSINESS: We make industrial equipment used in construction.", "thin": False}

    def fake_chat(system: str, user: str) -> dict:
        if "Fill a PTM trade idea template" in system:
            raise ValueError("Invalid control character at: line 3")
        if "qualitative" in system.lower() or "supports_outlier" in user:
            return {
                "supports_outlier": True,
                "red_flags": [],
                "kpis": ["backlog"],
                "operating_plan": "grow HVAC",
                "summary": "ok",
            }
        if "non_earnings" in user or "catalyst" in system.lower():
            return {"non_earnings": ["Investor day on 2026-09-20"], "meaningful": True, "reason": "dated event"}
        if "narrative" in system.lower() or "sector_tilts" in user:
            return {"narrative": "expansion", "sector_tilts": []}
        return {"markdown": "# fallback"}

    monkeypatch.setattr("ptm.pipeline.research_pack", fake_pack)
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    monkeypatch.setattr("ptm.pipeline.llm_available", lambda: True)
    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    # qual_mode="legacy": this test pins the template-fallback path; the
    # deep-dive pass needs live web research and is covered in test_deepsearch_verdict.py.
    ideas = generate_ideas(max_candidates=2, skip_llm=False, qual_mode="legacy")
    assert ideas
    for idea in ideas:
        assert idea.template_markdown.strip()
        assert idea.template_markdown.lstrip().startswith("#")


def test_run_writes_audit(monkeypatch):
    seed_pipeline_data()
    from ptm.io import read_df
    from ptm.pipeline import run

    monkeypatch.setattr("ptm.pipeline.ingest", lambda **kwargs: read_df(data_dir("curated", "universe.csv")))
    monkeypatch.setattr("ptm.llm.llm_available", lambda: False)
    monkeypatch.setattr("ptm.pipeline.llm_available", lambda: False)
    result = run(max_candidates=4, skip_llm=True)
    assert data_dir("curated", "audit.json").exists()
    assert "audit_findings" in result
    assert result["audit_report"].endswith("AUDIT.md")
    assert "funnel" in result
    assert result["ideas"] == 4
    assert result["candidates_long"] + result["candidates_short"] == result["candidates"]
    assert result["ideas_long"] + result["ideas_short"] == result["ideas"]


def _stub_ingest(monkeypatch):
    import pandas as pd

    monkeypatch.setattr("ptm.pipeline.fetch_macro_prices", lambda: {})
    monkeypatch.setattr("ptm.pipeline.scrape_ism", lambda **_: {})
    monkeypatch.setattr("ptm.pipeline.fetch_fred_macro", lambda: {})
    monkeypatch.setattr("ptm.pipeline.fetch_prices", lambda *_, **__: pd.DataFrame())


def _stub_edgar(monkeypatch, fetched: list):
    """One EDGAR fundamentals call per ticker, recorded."""

    def fake(ticker, with_guidance=True):
        fetched.append(ticker)
        return {
            "shares": 1_000_000.0,
            "eps_ttm": 2.0,
            "eps_prior_ttm": 1.8,
            "eps_basis": "4 quarterly filings",
            "report_dates": ["2026-05-05", "2026-02-04"],
            "guidance": None,
        }

    monkeypatch.setattr("ptm.ingest.edgar.company_fundamentals", fake)


def test_ingest_backfills_only_missing_tickers_from_edgar(monkeypatch):
    import pandas as pd

    universe = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "name": ["A", "B", "C"],
            "sector": ["Industrials"] * 3,
            "industry": ["Machinery"] * 3,
            "indices": ["sp500"] * 3,
        }
    )
    write_df(data_dir("curated", "universe.csv"), universe)
    _stub_ingest(monkeypatch)
    fetched: list[str] = []
    _stub_edgar(monkeypatch, fetched)

    ingest()
    assert set(fetched) == {"AAA", "BBB", "CCC"}
    out = read_df(data_dir("curated", "yahoo_fundamentals.csv"))
    assert set(out["ticker"].astype(str)) == {"AAA", "BBB", "CCC"}
    assert set(out["source"]) == {"edgar"}

    # Second pass adds only what is new.
    fetched.clear()
    universe4 = pd.concat(
        [universe, pd.DataFrame([{"ticker": "DDD", "name": "D", "sector": "Industrials", "industry": "Machinery", "indices": "sp500"}])],
        ignore_index=True,
    )
    write_df(data_dir("curated", "universe.csv"), universe4)
    ingest()
    assert fetched == ["DDD"]


def test_ingest_force_refetches_all_fundamentals(monkeypatch):
    import pandas as pd

    universe = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "name": ["A", "B"],
            "sector": ["Industrials"] * 2,
            "industry": ["Machinery"] * 2,
            "indices": ["sp500"] * 2,
        }
    )
    write_df(data_dir("curated", "universe.csv"), universe)
    _stub_ingest(monkeypatch)
    monkeypatch.setattr("ptm.pipeline.build_universe", lambda: universe)
    fetched: list[str] = []
    _stub_edgar(monkeypatch, fetched)

    ingest()
    assert sorted(fetched) == ["AAA", "BBB"]
    fetched.clear()
    ingest(force=True)
    assert sorted(fetched) == ["AAA", "BBB"]


def test_prices_are_fetched_before_fundamentals(monkeypatch):
    """Market cap and both P/E ratios are struck against the run date's close."""
    import pandas as pd

    universe = pd.DataFrame({"ticker": ["AAA"], "name": ["A"], "sector": ["Industrials"], "industry": ["M"], "indices": ["sp500"]})
    write_df(data_dir("curated", "universe.csv"), universe)
    order: list[str] = []
    monkeypatch.setattr("ptm.pipeline.fetch_macro_prices", lambda: {})
    monkeypatch.setattr("ptm.pipeline.scrape_ism", lambda **_: {})
    monkeypatch.setattr("ptm.pipeline.fetch_fred_macro", lambda: {})
    monkeypatch.setattr("ptm.pipeline.fetch_prices", lambda *_, **__: order.append("prices") or pd.DataFrame())
    monkeypatch.setattr(
        "ptm.pipeline.build_fundamentals",
        lambda universe, force=False: order.append("fundamentals") or pd.DataFrame({"ticker": ["AAA"]}),
    )
    ingest()
    assert order == ["prices", "fundamentals"]


def test_research_funnel_warns_on_thin_fundamentals():
    out = research_funnel(
        100,
        10,
        [Candidate(ticker="A", side=Side.LONG), Candidate(ticker="B", side=Side.SHORT)],
        [],
        [],
    )
    assert out["candidates"] == 2
    assert out["candidates_long"] == 1
    assert out["candidates_short"] == 1
    assert out["warnings"]
    assert "universe 100" in out["funnel"]
    assert "fundamentals 10" in out["funnel"]


def test_parallel_ideas_preserve_screen_rank_order(monkeypatch):
    """Completion order is nondeterministic; output order must not be."""
    import random
    import time as _time

    seed_pipeline_data()
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    monkeypatch.setattr("ptm.pipeline.llm_available", lambda: True)
    monkeypatch.setattr("ptm.pipeline.research_pack", lambda cand: {"text": "BUSINESS: widgets.", "thin": False})

    rng = random.Random(1)

    def jittery_chat(system, user, **kwargs):
        # Random latency so completion order differs from submission order.
        _time.sleep(rng.uniform(0, 0.03))
        if "supports_outlier" in user:
            return {"supports_outlier": True, "why": "ok", "evidence_for": ["x"], "evidence_against": []}
        if "Extract operating facts" in system:
            return {"business_in_one_line": "b", "operating_plan": "p", "kpis": ["backlog"], "red_flags": [], "quotes": []}
        if "non_earnings" in user:
            return {"non_earnings": [], "meaningful": False, "reason": "none"}
        if "views" in user or "narrative" in user:
            return {"views": [], "summary": "s", "narrative": "n", "ranked_tickers": [], "contradictions": []}
        return {"markdown": "# idea"}

    monkeypatch.setattr("ptm.llm.chat_json", jittery_chat)
    monkeypatch.setattr("ptm.group_review.chat_json", jittery_chat)
    monkeypatch.setattr("ptm.earnings.resolve", lambda t, r, ref=None, report_dates=None: __import__(
        "ptm.models", fromlist=["EarningsEstimate"]
    ).EarningsEstimate(ticker=t, date="2026-10-01", estimated=True, days_to_earnings=44, basis="test"))

    from ptm.pipeline import generate_ideas
    from ptm.quant import build_candidates
    from ptm.ranking import ordered_candidates

    # qual_mode="legacy": this test pins screen order through the legacy
    # verdict; the deep-dive pass is covered in test_deepsearch_verdict.py.
    ideas = generate_ideas(max_candidates=None, skip_llm=False, qual_mode="legacy")
    universe = read_df(data_dir("curated", "universe.csv"))
    fundamentals = read_df(data_dir("curated", "yahoo_fundamentals.csv"))
    expected = [c.ticker for c in ordered_candidates(build_candidates(universe, fundamentals))]
    assert [i.candidate.ticker for i in ideas] == expected
