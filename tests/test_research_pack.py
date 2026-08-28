from pathlib import Path

from ptm.ingest.company_research import research_pack
from ptm.ingest.edgar import extract_filing_sections, is_cover_page, is_exhibit99_name
from ptm.models import Candidate, Side
from ptm.llm import qualitative
from ptm.risk import normalize_earnings_date

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


def test_transcript_reaches_the_pack_text():
    """It was assembled into the payload but never rendered, so turning
    transcripts on would have silently changed nothing."""
    from ptm.ingest.company_research import _pack_text

    text = _pack_text({"transcript": "[Q2 2026, 2026-08-07] Revenue grew 51.7%."}, 12000)
    assert "Revenue grew 51.7%" in text
    assert "EARNINGS CALL:" in text


def test_pack_text_survives_an_empty_payload():
    from ptm.ingest.company_research import _pack_text

    assert isinstance(_pack_text({}, 12000), str)


def test_full_year_and_reported_cues_actually_match():
    """These regexes contained literal backspace bytes where \b was intended, so
    'FY2026' and 'was' matched nothing and the guidance parser returned None for
    every ticker in the universe. Guard the repair."""
    from ptm.ingest.edgar import FULL_YEAR_CUES, REPORTED_CUES

    for pattern in (FULL_YEAR_CUES, REPORTED_CUES):
        assert "\x08" not in pattern.pattern, "corrupted word boundary is back"
    assert FULL_YEAR_CUES.search("Updated FY2026 guidance")
    assert FULL_YEAR_CUES.search("full-year 2026 outlook")
    assert REPORTED_CUES.search("revenue was $87 million")
    assert not REPORTED_CUES.search("washing machines"), "the boundary must still bound"


def test_guidance_parser_accepts_net_income_per_share_phrasing():
    """"Adjusted Net Income per Diluted Share to $5.25" is EPS guidance. The
    parser wanted the literal words "earnings per share" and so read real
    guidance as none."""
    from ptm.ingest.edgar import parse_eps_guidance

    text = (
        "This momentum supports our third raise to FY2026 guidance, taking Adjusted Net "
        "Income per Diluted Share to $5.25."
    )
    out = parse_eps_guidance(text)
    assert out and out["midpoint"] == 5.25


def test_guidance_parser_is_not_defeated_by_bullets():
    """Releases are bulleted and the glyphs survive extraction. Splitting on
    sentence punctuation alone glued guidance to the next bullet, so the
    reported-results veto fired on the neighbour's wording."""
    from ptm.ingest.edgar import parse_eps_guidance

    text = (
        "Updated FY2026 guidance: adjusted earnings per share of $5.25 "
        "• Second Quarter Highlights • GMV grew 37.9% YoY."
    )
    assert parse_eps_guidance(text), "the trailing bullet must not veto the guidance"


def test_guidance_parser_rejects_a_revenue_figure():
    """SMCI guided "net sales in the range of $14.5 billion" and the parser
    reported it as 0.94 EPS against a 4.34 consensus - a 78% phantom gap."""
    from ptm.ingest.edgar import parse_eps_guidance

    text = (
        "Business Outlook: The Company expects net sales in the range of $14.5 billion "
        "to $15.0 billion for fiscal 2026 and earnings per share to grow."
    )
    out = parse_eps_guidance(text)
    assert out is None or out["midpoint"] < 100, out


def test_guidance_parser_rejects_a_prior_year_comparative():
    from ptm.ingest.edgar import parse_eps_guidance

    text = "FY 2022 diluted EPS and adjusted diluted EPS of $2.89, down 29 percent."
    assert parse_eps_guidance(text) is None
