from ptm.config import toml_settings
from ptm.gates import apply_process_gates, candidate_warnings, mcap_check, size_fraction
from ptm.models import Candidate, CatalystResult, IdeaState, PRMResult, QualResult, Side, TradeIdea


def test_long_mcap_band_is_enforced():
    ok, _ = mcap_check(Side.LONG, 5_000_000_000)
    assert ok
    ok, warn = mcap_check(Side.LONG, 50_000_000_000)
    assert not ok and "outside" in warn


def test_shorts_have_no_size_floor():
    """mcap_ok is the first ranking key, so a floor demoted every small short
    beneath every large cap rather than merely capping how many got in."""
    for cap in (5_000_000_000, 500_000_000, None):
        ok, warn = mcap_check(Side.SHORT, cap)
        assert ok and warn == "", f"market cap {cap} should not demote a short"


def test_short_floor_can_be_restored(monkeypatch):
    """The floor is off by configuration, not deleted."""
    import ptm.gates as gates

    base = dict(toml_settings()["filters"], short_mcap_min=20_000_000_000)
    monkeypatch.setattr(gates, "toml_settings", lambda: {"filters": base})
    assert mcap_check(Side.SHORT, 60_000_000_000)[0]
    ok, warn = mcap_check(Side.SHORT, 5_000_000_000)
    assert not ok and "below" in warn
    assert not mcap_check(Side.SHORT, None)[0], "unknown size fails a real floor"


def test_qual_gate_blocks():
    idea = TradeIdea(
        candidate=Candidate(ticker="X", side=Side.LONG),
        state=IdeaState.IDENTIFIED,
        qual=QualResult(supports_outlier=False, summary="denies"),
    )
    blocks = apply_process_gates(idea)
    assert any("outlier" in b for b in blocks)


def test_qual_none_does_not_block():
    idea = TradeIdea(
        candidate=Candidate(ticker="X", side=Side.LONG),
        qual=QualResult(supports_outlier=None, red_flags=["insufficient_evidence"]),
    )
    blocks = apply_process_gates(idea)
    assert not any("outlier" in b for b in blocks)


def test_catalyst_gate_without_timing():
    idea = TradeIdea(
        candidate=Candidate(ticker="X", side=Side.LONG),
        qual=QualResult(supports_outlier=True),
        catalysts=CatalystResult(tradeable=False, reason="none"),
    )
    blocks = apply_process_gates(idea)
    assert any("catalyst" in b for b in blocks)
    assert not any("timing" in b.lower() for b in blocks)


def test_r_score_and_timing_do_not_gate():
    idea = TradeIdea(
        candidate=Candidate(ticker="X", side=Side.LONG),
        prm=PRMResult(r_score=2.0, blocked=False),
    )
    blocks = apply_process_gates(idea)
    assert blocks == []
    amber = TradeIdea(candidate=Candidate(ticker="Y", side=Side.LONG))
    assert size_fraction(amber) == 1.0


def test_candidate_warnings_flags():
    huge = Candidate(ticker="X", side=Side.LONG, eg1=3.0, peg1=None)
    warns = candidate_warnings(huge)
    assert any("small numbers" in w for w in warns)
    assert any("PEG1" in w for w in warns)
    neg = Candidate(ticker="Y", side=Side.LONG, eg1=-0.1)
    assert any("non-positive" in w for w in candidate_warnings(neg))
