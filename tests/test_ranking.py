import pytest

from ptm.config import data_dir, ideas_dir
from ptm.io import read_json
from ptm.models import Candidate, Side
from ptm.ranking import ordered_candidates, rank_reason, write_ranking


def test_rank_reason_explains_pe_and_ism():
    cand = Candidate(
        ticker="AAA",
        side=Side.LONG,
        pe1=30.0,
        sector_pe1=20.0,
        ism_score=0.76,
        ism_why="Retail Trade growth",
        eg_case="long_case_1_acceleration",
        mcap_ok=True,
    )
    why = rank_reason(cand)
    assert "PE 30.0 vs sector 20.0" in why
    assert "ISM +0.76" in why
    assert "Retail Trade" in why
    assert "mcap in band" in why


def test_ordered_candidates_prefer_ism_then_growth():
    high = Candidate(ticker="HI", side=Side.LONG, mcap_ok=True, ism_score=1.5, eg1=0.1)
    low = Candidate(ticker="LO", side=Side.LONG, mcap_ok=True, ism_score=-1.0, eg1=0.4)
    short = Candidate(ticker="SH", side=Side.SHORT, mcap_ok=True, ism_score=0.9, eg1=-0.2)
    ordered = ordered_candidates([low, short, high])
    assert [c.ticker for c in ordered] == ["HI", "LO", "SH"]


def test_write_ranking_markdown_and_json():
    cands = [
        Candidate(ticker="L1", name="Long One", side=Side.LONG, mcap_ok=True, ism_score=1.0, pe1=22, sector_pe1=18),
        Candidate(ticker="S1", name="Short One", side=Side.SHORT, mcap_ok=True, ism_score=0.5, pe1=8, sector_pe1=18),
    ]
    path = write_ranking(cands, day="2026-08-17")
    assert path.name == "RANKING.md"
    text = path.read_text(encoding="utf-8")
    assert "Long #1/1" in text
    assert "Short #1/1" in text
    dumped = read_json(data_dir("curated", "ranking.json"))
    assert len(dumped["rows"]) == 2
    assert dumped["rows"][0]["ticker"] == "L1"
    assert ideas_dir("2026-08-17", "RANKING.md").exists()


def _ev(claim, pct=None, on="none", quantified=False):
    from ptm.models import EvidenceItem

    return EvidenceItem(claim=claim, impact_pct=pct, impact_on=on, quantified=quantified)


def _idea_with(side, for_items, against_items=()):
    from ptm.models import IdeaState, PRMResult, QualResult, TradeIdea

    return TradeIdea(
        candidate=Candidate(ticker="X", side=side, sector="Industrials", market_cap=50e9),
        state=IdeaState.TEMPLATED,
        prm=PRMResult(beta=1.0),
        qual=QualResult(
            supports_outlier=True,
            summary="s",
            evidence_for=list(for_items),
            evidence_against=list(against_items),
        ),
    )


def test_wrong_signed_reason_is_refiled_against_the_trade():
    """The real ARR case. Its only reason was '+216% earnings' offered as
    grounds to SHORT, and because magnitude caps at 30% it earned the maximum
    weight of 4.0 — putting it in the book on evidence that argued against it."""
    from ptm.ranking import CONTRADICTS_SIDE_FLAG, conviction, reconcile_sides

    idea = _idea_with(Side.SHORT, [_ev("EPS growth acceleration", 216.0, "earnings", True)])
    for_items, against_items, notes = reconcile_sides(idea.qual, Side.SHORT)
    assert for_items == []
    assert len(against_items) == 1
    assert any(CONTRADICTS_SIDE_FLAG in n for n in notes)
    assert conviction(idea) == -4.0, "the item must subtract, not add"


def test_correctly_signed_reasons_are_untouched():
    from ptm.ranking import conviction, reconcile_sides

    short = _idea_with(Side.SHORT, [_ev("revenue declining", -20.0, "revenue", True)])
    long = _idea_with(Side.LONG, [_ev("backlog driving revenue", 22.0, "revenue", True)])
    for side, idea in ((Side.SHORT, short), (Side.LONG, long)):
        kept, moved, notes = reconcile_sides(idea.qual, side)
        assert len(kept) == 1 and moved == [] and notes == []
        assert conviction(idea) > 1.0


def test_reconcile_is_idempotent():
    """Applied by the pipeline and again by conviction; must not double-move."""
    from ptm.ranking import reconcile_sides

    qual = _idea_with(Side.SHORT, [_ev("EPS up", 216.0, "earnings", True)]).qual
    for_items, against_items, _ = reconcile_sides(qual, Side.SHORT)
    qual.evidence_for, qual.evidence_against = for_items, against_items
    again_for, again_against, again_notes = reconcile_sides(qual, Side.SHORT)
    assert again_for == [] and len(again_against) == 1 and again_notes == []


def test_unquantified_reasons_are_never_refiled():
    """Only a stated magnitude carries a sign, so there is nothing to contradict."""
    from ptm.ranking import reconcile_sides

    qual = _idea_with(Side.SHORT, [_ev("management sounds confident")]).qual
    kept, moved, notes = reconcile_sides(qual, Side.SHORT)
    assert len(kept) == 1 and moved == [] and notes == []


def test_quantification_floor_blocks_a_pass_with_no_sized_reason():
    """The real OGN case: three true-sounding reasons, none of them a change."""
    from ptm.gates import quantification_gate

    ogn = _idea_with(Side.SHORT, [
        _ev("Decreasing demand for key product"),
        _ev("Pricing pressure in respiratory portfolio"),
        _ev("Volume declines due to revised medical guidelines"),
    ])
    blocks = quantification_gate(ogn)
    assert blocks and "quantified" in blocks[0]

    sized = _idea_with(Side.SHORT, [_ev("volumes down", -18.0, "revenue", True)])
    assert quantification_gate(sized) == []


def test_quantification_floor_does_not_double_punish_a_denied_verdict():
    """It is a bar on a pass, not a second way to fail."""
    from ptm.gates import quantification_gate
    from ptm.models import QualResult

    idea = _idea_with(Side.SHORT, [_ev("vague")])
    idea.qual = QualResult(supports_outlier=False, summary="denied")
    assert quantification_gate(idea) == []
    idea.qual = QualResult(supports_outlier=None, summary="skipped")
    assert quantification_gate(idea) == []


def test_wrong_signed_reason_cannot_satisfy_the_floor():
    from ptm.gates import quantification_gate

    idea = _idea_with(Side.SHORT, [_ev("EPS growth acceleration", 216.0, "earnings", True)])
    assert quantification_gate(idea), "a reason arguing the other way is not a sized reason"


def _drift_idea(ticker, side, up, down, change_90d, direction, themes=None):
    """An idea carrying measured revisions plus the verdict's direction call."""
    from ptm.models import IdeaState, PRMResult, QualResult, TradeIdea

    idea = TradeIdea(
        candidate=Candidate(ticker=ticker, side=side, sector="Industrials",
                            market_cap=50e9, eps1=5.0, eg1=0.2),
        state=IdeaState.TEMPLATED,
        prm=PRMResult(beta=1.0),
        qual=QualResult(
            supports_outlier=True, summary="s",
            evidence_for=[_ev("sized reason", 20.0, "earnings", True)],
            filing_direction=direction,
            direction_basis="FY guidance raised",
            momentum_durability="intact",
            themes=list(themes or []),
        ),
    )
    idea.extra["expectations"] = {
        "revisions": {
            "available": True,
            "analysts_up_30d": up,
            "analysts_down_30d": down,
            "change_90d_pct": change_90d,
            "change_30d_pct": change_90d,
        }
    }
    return idea


def _mom_idea(ticker, side, up, down, change_90d, direction, themes=None):
    """An idea carrying measured revisions plus the verdict's direction call."""
    from ptm.models import IdeaState, PRMResult, QualResult, TradeIdea

    idea = TradeIdea(
        candidate=Candidate(ticker=ticker, side=side, sector="Industrials",
                            market_cap=50e9, eps1=5.0, eg1=0.2),
        state=IdeaState.TEMPLATED,
        prm=PRMResult(beta=1.0),
        qual=QualResult(
            supports_outlier=True, summary="s",
            evidence_for=[_ev("sized reason", 20.0, "earnings", True)],
            filing_direction=direction,
            direction_basis="FY guidance raised",
            momentum_durability="intact",
            themes=list(themes or []),
        ),
    )
    idea.extra["expectations"] = {
        "revisions": {
            "available": True, "analysts_up_30d": up, "analysts_down_30d": down,
            "change_90d_pct": change_90d, "change_30d_pct": change_90d,
            # Required: a percentage change is refused on a near-zero or
            # sign-flipped base, so a fixture without levels measures nothing.
            "eps_current": 5.0, "eps_d90": 4.5,
        }
    }
    return idea


def test_momentum_leads_the_ranking():
    """Quant is the filter; qualitative factors order the book, and revision
    momentum leads them."""
    from ptm.ranking import ordered_ideas

    strong = _mom_idea("STRONG", Side.LONG, 8, 0, 22.0, "improving")
    strong.candidate.ism_score = -1.0        # worst sector tilt
    weak = _mom_idea("WEAK", Side.LONG, 0, 0, 0.0, "silent")
    weak.candidate.ism_score = 2.0           # best sector tilt
    order = [i.candidate.ticker for i in ordered_ideas([weak, strong])]
    assert order[0] == "STRONG", order


def test_revisions_against_the_trade_rank_below_no_data():
    """Estimates moving the wrong way is worse than no signal at all."""
    from ptm.ranking import momentum_edge_pct

    against = _mom_idea("AGAINST", Side.LONG, 0, 8, -22.0, "deteriorating")
    assert momentum_edge_pct(against) == -22.0
    quiet = _mom_idea("QUIET", Side.LONG, 0, 0, 0.0, "silent")
    assert momentum_edge_pct(quiet) is None


def test_theme_exposure_breaks_ties_but_never_leads():
    from ptm.ranking import ordered_ideas, theme_score

    themed = _mom_idea("THEME", Side.LONG, 4, 0, 8.0, "improving",
                       themes=["AI and data centre (40)"])
    plain = _mom_idea("PLAIN", Side.LONG, 4, 0, 8.0, "improving")
    assert theme_score(themed) > theme_score(plain) == 0.0
    assert [i.candidate.ticker for i in ordered_ideas([plain, themed])][0] == "THEME"

    # A theme must not rescue a name with weaker momentum.
    stronger = _mom_idea("STRONG", Side.LONG, 9, 0, 25.0, "improving")
    weak_themed = _mom_idea("WEAK", Side.LONG, 2, 0, 4.0, "improving",
                            themes=["AI and data centre (60)"])
    assert [i.candidate.ticker for i in ordered_ideas([weak_themed, stronger])][0] == "STRONG"


def test_the_filings_veto_is_applied_as_a_gate():
    from ptm.gates import revision_veto_gate

    contradicting = _mom_idea("VETO", Side.LONG, 8, 0, 20.0, "deteriorating")
    assert revision_veto_gate(contradicting), "estimates up, filings down -> block"
    agreeing = _mom_idea("OK", Side.LONG, 8, 0, 20.0, "improving")
    assert revision_veto_gate(agreeing) == []
    silent = _mom_idea("QUIET", Side.LONG, 8, 0, 20.0, "silent")
    assert revision_veto_gate(silent) == []


def test_the_veto_does_not_fire_on_a_denied_verdict():
    from ptm.gates import revision_veto_gate
    from ptm.models import QualResult

    idea = _mom_idea("DENIED", Side.LONG, 8, 0, 20.0, "deteriorating")
    idea.qual = QualResult(supports_outlier=False, summary="denied", filing_direction="deteriorating")
    assert revision_veto_gate(idea) == []
