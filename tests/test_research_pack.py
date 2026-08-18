from pathlib import Path

from ptm.ingest.company_research import research_pack
from ptm.ingest.edgar import extract_filing_sections, is_cover_page, is_exhibit99_name
from ptm.models import Candidate, Side
from ptm.llm import qualitative
from ptm.timing_prm import normalize_earnings_date

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


TEN_Q = (
    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION "
    "Item 1. Business We manufacture HVAC equipment for commercial buildings and sell through distributors. "
    "Item 1A. Risk Factors Commodity prices and labor shortages could hurt results. "
    "Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations "
    "Revenue grew 12 percent on volume in the HVAC segment as data center demand increased. "
    "Gross margin expanded 80 basis points and backlog rose to a record level. "
    "Item 3. Quantitative and Qualitative Disclosures About Market Risk Interest rate risk is modest."
)

TOC_MDA = "Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations 43"

COVER_8K = (
    "false 0001002910 iso4217:USD xbrli:shares UNITED STATES SECURITIES AND EXCHANGE COMMISSION "
    "FORM 8-K CURRENT REPORT Item 9.01 Financial Statements and Exhibits."
)

EX99 = (
    "Exhibit 99.1 Earnings Release. Net income was $523 million. Management reaffirmed full-year EPS guidance "
    "and announced a $2 billion data center interconnection plan for 2026-2027."
)


def test_filing_sections_extract_real_mda():
    sections = extract_filing_sections(TEN_Q, max_chars=800)
    assert "HVAC" in sections["business"]
    assert "data center" in sections["mda"].lower()
    assert "12 percent" in sections["mda"]
    assert len(sections["mda"]) > 200 or "Revenue grew" in sections["mda"]


def test_toc_mda_is_too_short_for_research():
    sections = extract_filing_sections(
        "Preface. " + TOC_MDA + " Item 3. Quantitative",
        max_chars=800,
    )
    assert len(sections["mda"].strip()) < 200


def test_normalize_yahoo_calendar_shapes():
    assert normalize_earnings_date("[datetime.date(2026, 7, 31)]") == "2026-07-31"
    assert normalize_earnings_date("2026-10-30") == "2026-10-30"


def test_research_pack_thin_and_fat(monkeypatch):
    monkeypatch.setattr("ptm.ingest.company_research.company_facts", lambda ticker: {})
    monkeypatch.setattr(
        "ptm.ingest.company_research.filing_sections",
        lambda ticker, max_chars=4000: {"business": "", "mda": ""},
    )
    monkeypatch.setattr("ptm.ingest.company_research.latest_earnings_exhibit", lambda ticker, max_chars=4000: "")
    thin = research_pack(Candidate(ticker="ZZ", side=Side.LONG), force=True)
    assert thin["thin"] is True

    monkeypatch.setattr(
        "ptm.ingest.company_research.filing_sections",
        lambda ticker, max_chars=4000: {"business": TEN_Q[40:400], "mda": TEN_Q[200:]},
    )
    monkeypatch.setattr("ptm.ingest.company_research.latest_earnings_exhibit", lambda ticker, max_chars=4000: EX99)
    fat = research_pack(Candidate(ticker="AEE", side=Side.SHORT, sector="Utilities"), force=True)
    assert fat["thin"] is False
    assert "EX-99" in fat["text"] or "Earnings Release" in fat["text"]
    assert fat["earnings_exhibit"].startswith("Exhibit 99.1")


def test_toc_then_body_uses_item1_and_mda():
    text = (FIXTURES / "toc_then_body.txt").read_text(encoding="utf-8")
    sections = extract_filing_sections(text, max_chars=1200)
    assert "HVAC" in sections["business"]
    assert "data center" in sections["mda"].lower()
    assert "12 percent" in sections["mda"]
    assert len(sections["mda"]) >= 200


def test_cover_page_rejected_exhibit_kept():
    cover = (FIXTURES / "cover_8k.txt").read_text(encoding="utf-8")
    exhibit = (FIXTURES / "ex99_1.txt").read_text(encoding="utf-8")
    assert is_cover_page(cover) is True
    assert is_cover_page(exhibit) is False
    assert is_exhibit99_name("ex99-1.htm") is True
    assert is_exhibit99_name("aee-8k.htm") is False


def test_pack_is_edgar_only(monkeypatch):
    """No Yahoo summary, no headlines: an empty Item 1 stays empty rather than
    being backfilled from a vendor description."""
    monkeypatch.setattr(
        "ptm.ingest.company_research.company_facts",
        lambda ticker: {"revenue": 1.0, "net_income": 1.0},
    )
    monkeypatch.setattr(
        "ptm.ingest.company_research.filing_sections",
        lambda ticker, max_chars=4000: {"business": "", "mda": ""},
    )
    monkeypatch.setattr("ptm.ingest.company_research.latest_earnings_exhibit", lambda ticker, max_chars=4000: "")
    pack = research_pack(Candidate(ticker="AEE", side=Side.SHORT), force=True)
    assert pack["business"] == ""
    assert pack["summary"] == ""
    assert pack["headlines"] == []


def test_no_yfinance_import_in_the_research_pack():
    import ptm.ingest.company_research as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "yfinance" not in source
    assert "yf.Ticker" not in source
    assert not hasattr(module, "_yahoo_pack")


def test_qual_null_only_when_pack_empty(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    empty = qualitative(Candidate(ticker="X", side=Side.LONG), "   ", thin=True)
    assert empty.supports_outlier is None
    assert "insufficient_evidence" in empty.red_flags
