from ptm.gates import apply_process_gates, candidate_warnings, mcap_check, size_fraction
from ptm.models import Candidate, CatalystResult, IdeaState, PRMResult, QualResult, Side, TradeIdea


def test_mcap_bands():
    ok, _ = mcap_check(Side.LONG, 5_000_000_000)
    assert ok
    ok, warn = mcap_check(Side.SHORT, 5_000_000_000)
    assert not ok
    assert "below" in warn


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
