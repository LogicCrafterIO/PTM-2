from pathlib import Path

from ptm.ingest.edgar import extract_filing_sections
from ptm.ingest.ism import parse_ism_report, _parse_registered
from ptm.ingest.ism_sectors import apply_ism_tilts, compute_sector_tilts, gics_for_ism, split_quota
from ptm.models import Candidate, Side

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_july_headlines():
    sample = (
        "The Manufacturing PMI registered 55.6 percent in July. "
        "The Services PMI registered 54.1 percent, the 25th consecutive month in expansion."
    )
    assert _parse_registered(sample, ("Manufacturing",)) == 55.6
    assert _parse_registered(sample, ("Services", "NMI")) == 54.1


def test_parse_july_manufacturing_fixture():
    text = (FIXTURES / "ism_july_manufacturing.md").read_text(encoding="utf-8")
    report = parse_ism_report(text, "pmi")
    assert report["headline"] == 55.6
    assert report["components"]["new_orders"]["value"] == 56.7
    assert report["components"]["production"]["value"] == 58.5
    assert "Chemical Products" in report["industries"]["contraction"]
    assert report["industries"]["growth"][0] == "Printing & Related Support Activities"
    assert "Chemical Products" in report["new_orders_industries"]["contraction"]
    industries = {row["industry"] for row in report["comments"]}
    assert "Chemical Products" in industries
    assert any("opportunistic" in row["quote"] for row in report["comments"])


def test_parse_july_services_fixture():
    text = (FIXTURES / "ism_july_services.md").read_text(encoding="utf-8")
    report = parse_ism_report(text, "services")
    assert report["headline"] == 54.1
    assert report["components"]["new_orders"]["value"] == 57.2
    assert report["components"]["business_activity"]["value"] == 59.1
    assert "Retail Trade" in report["industries"]["growth"]
    assert "Health Care & Social Assistance" in report["industries"]["contraction"]


def test_chemicals_map_to_materials_short():
    text = (FIXTURES / "ism_july_manufacturing.md").read_text(encoding="utf-8")
    report = parse_ism_report(text, "pmi")
    tilts = compute_sector_tilts({"pmi": 55.6, "manufacturing": report, "services": {}}, pmi=55.6)
    assert gics_for_ism("Chemical Products") == "Materials"
    chem = next(row for row in tilts if row.get("industry") == "Chemical Products")
    assert chem["tilt"] == "short"
    assert chem["sector"] == "Materials"
    short = Candidate(ticker="DOW", side=Side.SHORT, sector="Materials", industry="Specialty Chemicals")
    long = Candidate(ticker="LIN", side=Side.LONG, sector="Materials", industry="Specialty Chemicals")
    apply_ism_tilts([short, long], tilts)
    assert short.ism_score > long.ism_score
    assert long.ism_tilt == "short"


def test_split_quota_balances_sides():
    longs = [
        Candidate(ticker=f"L{i}", side=Side.LONG, mcap_ok=True, eg1=1 - i * 0.1, ism_score=0.2)
        for i in range(6)
    ]
    shorts = [
        Candidate(ticker=f"S{i}", side=Side.SHORT, mcap_ok=True, eg1=-0.2 - i * 0.05, ism_score=0.3)
        for i in range(6)
    ]
    chosen = split_quota(longs + shorts, 4)
    assert len(chosen) == 4
    assert sum(1 for c in chosen if c.side == Side.LONG) == 2
    assert sum(1 for c in chosen if c.side == Side.SHORT) == 2


def test_apply_tilts_aligns_short_with_contraction():
    tilts = [{"sector": "Materials", "tilt": "short", "score": -0.8, "why": "Chemical Products"}]
    long_chem = Candidate(ticker="LIN", side=Side.LONG, sector="Materials")
    short_chem = Candidate(ticker="DOW", side=Side.SHORT, sector="Materials")
    apply_ism_tilts([long_chem, short_chem], tilts)
    assert short_chem.ism_score > long_chem.ism_score


def test_filing_section_extract():
    text = (
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION "
        "Item 1. Business We make widgets and sell them to hospitals. "
        "Item 1A. Risk Factors Lots of risk. "
        "Item 7. Management’s Discussion and Analysis Revenue grew 12 percent on volume "
        "in the core hospital-supply segment as utilization recovered and backlog converted. "
        "Gross margin expanded and management reaffirmed full-year guidance for the year. "
        "Item 7A. Quantitative and Qualitative Disclosures"
    )
    sections = extract_filing_sections(text, max_chars=800)
    assert "widgets" in sections["business"].lower()
    assert "volume" in sections["mda"].lower()
