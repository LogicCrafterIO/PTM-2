"""The deep-dive → QualResult adapter, and the pipeline wired to it.

The adapter is what makes the deep dive a drop-in replacement for the EDGAR-pack
qualitative pass: same QualResult fields, same gates, same ranking inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ptm.deepsearch.models import (
    BearPoint,
    BullPoint,
    DebateRound,
    DeepResearch,
    DeepResult,
    Driver,
    SearchFinding,
    SourceRef,
    Thesis,
)
from ptm.deepsearch.verdict import (
    _verify_quantified,
    qual_from_deepdive,
    stance_supports,
)
from ptm.models import Candidate, EvidenceItem, Side
from tests.conftest import seed_pipeline_data


def _dive(stance: str = "constructive", side_name: str = "TEST") -> DeepResult:
    findings = DeepResearch(
        ticker=side_name,
        queries_run=["q1"],
        findings=[
            SearchFinding(claim="Revenue up 40% y/y", source=SourceRef(title="PR", url="https://example.com/1")),
            SearchFinding(claim="Backlog up 22%", source=SourceRef(title="Call", url="https://example.com/2")),
        ],
    )
    return DeepResult(
        ticker=side_name,
        name="Test Corp",
        sector="Industrials",
        as_of=datetime.now(timezone.utc).date().isoformat(),
        research=findings,
        thesis=Thesis(
            stance=stance,
            thesis="Acceleration is real.",
            drivers=[Driver(name="Pricing power", direction="tailwind", evidence="backlog up 22%", confidence="high")],
            debate=[
                DebateRound(
                    driver="Pricing power",
                    bull="b",
                    bear="r",
                    verdict="bull wins",
                    verdict_side="bull",
                )
            ],
            bull_case=[BullPoint(point="Backlog up 22% after price increases", evidence="call transcript", strength="strong")],
            bear_case=[BearPoint(point="Rivals undercut on price next year", evidence="industry note", severity="material")],
            falsifiers=["backlog flat next print"],
            confidence="medium",
            confidence_why="consistent sources",
        ),
    )


def _candidate(side: Side) -> Candidate:
    return Candidate(
        ticker="TEST",
        name="Test Corp",
        sector="Industrials",
        side=side,
        pe1=30.0,
        sector_pe1=15.0,
        eg1=0.5,
        eps1=2.0,
        eps0=1.8,
    )


def test_stance_supports_side_aware():
    assert stance_supports("constructive", Side.LONG) is True
    assert stance_supports("cautious", Side.SHORT) is True
    assert stance_supports("cautious", Side.LONG) is False
    assert stance_supports("constructive", Side.SHORT) is False
    # A balanced dive supports NEITHER side's trade; unclear defers.
    assert stance_supports("balanced", Side.LONG) is False
    assert stance_supports("balanced", Side.SHORT) is False
    assert stance_supports("unclear", Side.LONG) is None
    assert stance_supports("", Side.SHORT) is None


def test_score_aggregation_mirrors_long_short():
    """Fixed weights, driver confidence scaling, and the long/short mirror."""
    from ptm.deepsearch.verdict import aggregate_scores, score_debate, score_supports

    thesis = Thesis(
        stance="balanced",
        drivers=[
            Driver(name="Valuation premium unjustified", direction="headwind", confidence="high"),
            Driver(name="Catalyst: FDA approval", direction="tailwind", confidence="medium"),
            Driver(name="Competitive moat widening", direction="tailwind", confidence="high"),
            Driver(name="Litigation risk", direction="headwind", confidence="high"),
            Driver(name="Margin trajectory", direction="headwind", confidence="medium"),
        ],
        debate=[
            DebateRound(driver="Valuation premium unjustified", bull="b", bear="r", verdict="bull", verdict_side="bull"),
            DebateRound(driver="Catalyst: FDA approval slips", bull="b", bear="r", verdict="bear", verdict_side="bear"),
            DebateRound(driver="Competitive moat widening", bull="b", bear="r", verdict="bull", verdict_side="bull"),
            DebateRound(driver="Litigation risk", bull="b", bear="r", verdict="tie", verdict_side="tie"),
            DebateRound(driver="Margin trajectory", bull="b", bear="r", verdict="bear", verdict_side="bear"),
        ],
    )
    rows = score_debate(thesis, None)  # no adapter: deterministic off verdict_side + confidence
    # bull high: +1.5*1.0*0.30 = +0.45 ; bear medium catalysts: -1.5*0.7*0.20 = -0.21
    # bull high competitive: +1.5*1.0*0.12 = +0.18 ; tie: 0 ; bear medium fundamentals: -1.5*0.7*0.30 = -0.315
    agg = aggregate_scores(rows)
    assert abs(agg["s"] - 0.105) < 1e-6
    # single bull-won valuation driver at +1.5 base: ((0.45/0.3)+2)/4*10 = 8.8;
    # single bear-won medium catalyst driver: ((-0.21/0.2)+2)/4*10 = 2.4
    assert agg["valuation"] == 8.8 and agg["catalysts"] == 2.4 and agg["risk"] == 5.0
    assert agg["long"] + agg["short"] == 10.0
    # The balanced band defers both sides; beyond the threshold it is side-decisive.
    assert score_supports(agg["s"], Side.LONG, 0.6) is None
    assert score_supports(agg["s"], Side.SHORT, 0.6) is None
    assert score_supports(0.7, Side.LONG, 0.6) is True
    assert score_supports(0.7, Side.SHORT, 0.6) is False
    assert score_supports(-0.7, Side.SHORT, 0.6) is True  # the same dive, flipped


def test_scorecard_rendered_in_idea_markdown():
    from ptm.models import DriverScore, QualResult

    from ptm.deepsearch.render import _scorecard_md

    qual = QualResult(
        score_s=1.2,
        score_long=8.0,
        score_short=2.0,
        score_valuation=6.5,
        driver_scores=[
            DriverScore(driver="Pricing power", category="fundamentals", score=1.5, verdict_side="bull", confidence="high", weight=0.3, contribution=0.45, why="backlog up"),
        ],
    )
    md = "\n".join(_scorecard_md(qual))
    assert "S = +1.20" in md
    assert "long thesis 8.0/10" in md and "short thesis 2.0/10" in md
    assert "| Pricing power | fundamentals | bull | +1.50 | high | 30% | +0.45 |" in md
    # absent categories read n/a instead of a fabricated number
    assert "competitive n/a" in md


def test_verify_quantified_strips_invented_magnitudes():
    text = "Backlog up 22% year over year; revenue up 40%."
    ok = EvidenceItem(claim="backlog", impact_pct=22.0, impact_on="earnings", quantified=True)
    invented = EvidenceItem(claim="growth", impact_pct=17.0, impact_on="revenue", quantified=True)
    plain = EvidenceItem(claim="strong brand")
    out, stripped = _verify_quantified([ok, invented, plain], text)
    assert stripped == 1
    assert out[0].quantified is True and out[0].impact_pct == 22.0
    # Stripped of the flag and magnitude, the claim itself is kept — visible,
    # just not allowed to carry invented precision into the conviction score.
    assert out[1].quantified is False and out[1].impact_pct is None
    assert out[1].claim == "growth"
    assert plain.quantified is False


def test_fallback_maps_stance_without_llm(monkeypatch):
    monkeypatch.setattr("ptm.deepsearch.verdict.llm_available", lambda: False)
    qual = qual_from_deepdive(_dive("constructive"), _candidate(Side.LONG), "Backlog up 22%")
    assert qual.supports_outlier is True
    assert qual.filing_direction == "improving"
    assert qual.themes is not None
    # The bull case IS the evidence for a long; flipped for a short.
    assert any("Backlog" in item.claim or "backlog" in item.claim for item in qual.evidence_for)


def test_fallback_respects_side_flipping(monkeypatch):
    monkeypatch.setattr("ptm.deepsearch.verdict.llm_available", lambda: False)
    short_qual = qual_from_deepdive(_dive("cautious"), _candidate(Side.SHORT), "Backlog up 22%")
    assert short_qual.supports_outlier is True
    assert any("Rivals" in item.claim for item in short_qual.evidence_for)


def test_adapter_call_produces_structured_verdict(monkeypatch):
    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["system"] = system
        seen["user"] = user
        assert kwargs.get("model")  # runs on the verdict model
        return {
            "filing_direction": "improving",
            "direction_basis": "backlog up 22%",
            "momentum_durability": "building",
            "durability_basis": "guidance raised twice",
            "supports_outlier": True,
            "why": "Prices up and backlog up 22%; demand is accelerating.",
            "denial_reason": "",
            "evidence_for": [
                {"claim": "backlog up 22%", "metric": "backlog", "impact_pct": 22, "impact_on": "earnings", "quantified": True},
                {"claim": "revenue up 40% y/y", "metric": "revenue", "impact_pct": 40, "impact_on": "revenue", "quantified": True},
            ],
            "evidence_against": [
                # Plausible in size (under the 500 cap) but absent from the dive
                # text: the mechanical verifier is what must catch this one.
                {"claim": "rivals cut prices", "impact_pct": 350, "impact_on": "revenue", "quantified": True},
            ],
            "kpis": ["backlog", "pricing"],
            "operating_plan": "add capacity in 2027",
            # One per debate round; the model scores magnitude and category, the
            # weights are applied in code.
            "driver_scores": [
                {"driver": "Pricing power", "category": "fundamentals", "score": 2.0, "why": "decisive backlog and pricing evidence"},
            ],
        }

    monkeypatch.setattr("ptm.deepsearch.verdict.chat_json", fake_chat)
    monkeypatch.setattr("ptm.deepsearch.verdict.llm_available", lambda: True)
    text = "Backlog up 22% after price increases. Revenue up 40% y/y."
    qual = qual_from_deepdive(_dive(), _candidate(Side.LONG), text)
    # The score decides: one decisively bull-won driver, fundamentals weight
    # 0.30, driver confidence high -> S = +2.0 * 1.0 * 0.30 = +0.60.
    assert qual.score_s == 0.6
    assert qual.score_long == 6.5 and qual.score_short == 3.5
    assert qual.score_fundamentals == 10.0 and qual.score_valuation is None
    assert len(qual.driver_scores) == 1 and qual.driver_scores[0].contribution == 0.6
    assert qual.supports_outlier is True  # |S| = threshold -> side-decisive
    assert qual.filing_direction == "improving"
    assert qual.momentum_durability == "building"
    # quantified=True survives only where the figure appears in the dive text.
    assert [i.impact_pct for i in qual.evidence_for] == [22.0, 40.0]
    assert qual.evidence_for[0].quantified is True
    # 999 never appears in the text: flagged, stripped, claim kept.
    assert any("unverifiable_magnitude_stripped" in flag for flag in qual.red_flags)
    assert qual.evidence_against[0].quantified is False
    assert qual.operating_plan == "add capacity in 2027"
    assert qual.why.startswith("[dive: constructive | S=+0.60]")
    assert "verdict" not in (qual.denial_reason or "")


def test_adapter_failure_falls_back(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider 500")

    monkeypatch.setattr("ptm.deepsearch.verdict.chat_json", boom)
    monkeypatch.setattr("ptm.deepsearch.verdict.llm_available", lambda: True)
    qual = qual_from_deepdive(_dive(), _candidate(Side.SHORT), "Backlog up 22%")
    assert any("verdict_adapter_failed" in flag for flag in qual.red_flags)
    assert qual.supports_outlier is False  # constructive dive does not help a short


def test_failed_dive_defers(monkeypatch):
    monkeypatch.setattr("ptm.deepsearch.verdict.llm_available", lambda: True)
    monkeypatch.setattr("ptm.deepsearch.verdict.chat_json", lambda *a, **k: {})
    result = _dive()
    result.error = "no findings from web research"
    result.thesis = None
    result.llm_used = False
    qual = qual_from_deepdive(result, _candidate(Side.LONG), "")
    assert qual.supports_outlier is None
    assert any("deepdive_incomplete" in flag for flag in qual.red_flags)


def test_quota_detection():
    from ptm.llm import is_quota_error, is_quota_text

    assert is_quota_error(RuntimeError("connection reset")) is False
    exc429 = RuntimeError("429 too many requests")
    exc429.status_code = 429
    assert is_quota_error(exc429) is False  # 429 is a throttle, not quota
    quota = type("Q", (Exception,), {"status_code": 402})()
    assert is_quota_error(quota) is True
    assert is_quota_text("provider says: quota exceeded for this key") is True
    assert is_quota_text("usage limit reached, try later") is True
    assert is_quota_text("connection reset") is False


def test_dive_retry_ladder_outlasts_throttling(monkeypatch):
    """A 429-dead dive is retried whole, then succeeds; quota waits the full pause."""
    import ptm.pipeline as pl
    from ptm.llm import is_quota_error
    from ptm.deepsearch.models import DeepResult

    ok = DeepResult(ticker="TICK")
    throttles = {"n": 0}

    def flaky(ticker, **kwargs):
        throttles["n"] += 1
        if throttles["n"] < 3:
            exc = RuntimeError("429 too many requests")
            exc.status_code = 429
            raise exc
        return ok

    monkeypatch.setattr(pl, "run_deep_dive", flaky)
    sleeps: list[float] = []
    result = pl.run_deep_dive_with_retries("TICK", sleeper=sleeps.append, retries=3, wait_s=120)
    assert result is ok
    assert throttles["n"] == 3
    assert len(sleeps) == 2  # two failed attempts, then success
    assert all(0 < s <= 60 for s in sleeps)  # throttle pauses stay short

    # Quota gets the full configured wait, and an error-y RESULT (a dive that
    # came back with error set instead of raising) walks the same ladder.
    quota_calls = {"n": 0}

    def quota_dives(ticker, **kwargs):
        quota_calls["n"] += 1
        if quota_calls["n"] < 2:
            return DeepResult(ticker=ticker, error="402 payment required: quota exceeded")
        return ok

    monkeypatch.setattr(pl, "run_deep_dive", quota_dives)
    sleeps2: list[float] = []
    out = pl.run_deep_dive_with_retries("TICK", sleeper=sleeps2.append, retries=2, wait_s=120)
    assert out.error == ""
    assert sleeps2 == [120.0]
    assert is_quota_error(RuntimeError("quota exceeded")) is True


def test_dive_retry_exhaustion_raises_last_failure(monkeypatch):
    """Retries spent and still failing: the error resurfaces to the idea."""
    import ptm.pipeline as pl
    from ptm.deepsearch.models import DeepResult

    calls = {"n": 0}

    def always_dead(ticker, **kwargs):
        calls["n"] += 1
        return DeepResult(ticker=ticker, error="no findings from web research")

    monkeypatch.setattr(pl, "run_deep_dive", always_dead)
    sleeps: list[float] = []
    out = pl.run_deep_dive_with_retries("TICK", sleeper=sleeps.append, retries=2, wait_s=30)
    # A permanently empty research pass isn't quota — short pauses, budget spent,
    # final result returned with its error so the idea reads as deferred.
    assert calls["n"] == 3
    assert out.error == "no findings from web research"
    assert len(sleeps) == 2 and all(s <= 20 for s in sleeps)


def test_pipeline_uses_deep_dive_qual(monkeypatch):
    """End to end: the dive's stance becomes the gate, the dive text the idea file."""
    seed_pipeline_data()
    dive = _dive("constructive")

    calls = {"dives": 0}

    def fake_run_deep_dive(ticker, **kwargs):
        calls["dives"] += 1
        return dive

    def adapter_chat(system, user, **kwargs):
        return {
            "filing_direction": "improving",
            "direction_basis": "backlog +22%",
            "momentum_durability": "building",
            "durability_basis": "guidance raised",
            "supports_outlier": True,
            "why": "Demand accelerates and the backlog quantifies it.",
            "evidence_for": [
                {"claim": "backlog up 22%", "metric": "backlog", "impact_pct": 22, "impact_on": "earnings", "quantified": True}
            ],
            "evidence_against": [],
            "kpis": ["backlog", "pricing"],
            "operating_plan": "expand capacity",
        }

    def other_chat(system, user, **kwargs):
        if "non-earnings catalysts" in system:
            return {
                "non_earnings": [{"event": "Investor day", "date": "2026-09-20", "why": "guidance update"}],
                "meaningful": True,
                "reason": "dated event",
            }
        if "sector_tilts" in user or "narrative" in system.lower():
            return {"narrative": "expansion", "sector_tilts": []}
        return {"views": [], "summary": "s", "narrative": "n", "ranked_tickers": [], "contradictions": []}

    monkeypatch.setattr("ptm.pipeline.run_deep_dive", fake_run_deep_dive)
    monkeypatch.setattr("ptm.pipeline.qual_from_deepdive", qual_from_deepdive)
    monkeypatch.setattr("ptm.deepsearch.verdict.chat_json", adapter_chat)
    monkeypatch.setattr("ptm.deepsearch.verdict.llm_available", lambda: True)
    monkeypatch.setattr("ptm.llm.chat_json", other_chat)
    monkeypatch.setattr("ptm.pipeline.llm_available", lambda: True)
    monkeypatch.setattr(
        "ptm.pipeline.market_expectations",
        lambda ticker, earnings_date: {
            "revisions": {
                "available": True,
                "analysts_up_30d": 3,
                "analysts_down_30d": 0,
                "eps_current": 2.0,
                "eps_d90": 1.0,
                "change_90d_pct": 200.0,
                "change_30d_pct": 60.0,
            }
        },
    )
    monkeypatch.setattr("ptm.group_review.chat_json", other_chat)

    from ptm.pipeline import generate_ideas

    ideas = generate_ideas(max_candidates=3, skip_llm=False, qual_mode="deepdive")
    assert calls["dives"] == 3
    assert ideas
    for idea in ideas:
        assert idea.extra.get("deepdive", {}).get("stance") == "constructive"
        assert idea.template_markdown.strip().startswith("#")
        assert "deep qualitative dive" in idea.template_markdown  # embedded REPORT.md
        assert not idea.template_markdown.lstrip().startswith("{")
        assert idea.qual is not None
    from ptm.config import ideas_dir

    first = ideas[0]
    report = ideas_dir() / first.extra["deepdive"]["report"]
    assert report.exists() and report.read_text(encoding="utf-8").startswith("#")