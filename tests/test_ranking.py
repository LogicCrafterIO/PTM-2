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
