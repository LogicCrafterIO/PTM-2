from __future__ import annotations

from ptm.deepsearch.models import (
    BearPoint,
    BullPoint,
    Catalyst,
    DebateRound,
    DeepResearch,
    DeepResult,
    Driver,
    MacroImplication,
    MacroView,
    SearchFinding,
    SourceRef,
    Thesis,
)
from ptm.deepsearch.render import render_markdown


def make_result() -> DeepResult:
    src = SourceRef(title="Q2 press release", url="https://example.com/q2")
    research = DeepResearch(
        ticker="TEST",
        as_of="2026-08-29",
        queries_run=["TEST latest earnings", "TEST competitors market share"],
        findings=[
            SearchFinding(claim="Revenue grew 93% y/y", source=src, category="business", dated="2026-08-03"),
            SearchFinding(claim="Competitor X launched a rival product", source=src, category="competition"),
            SearchFinding(claim="Customer Y terminated its contract", source=src, category="catalyst"),
        ],
        sources=[src],
        search_used=True,
    )
    thesis = Thesis(
        stance="constructive",
        thesis="Demand is accelerating faster than competitors can respond.",
        drivers=[
            Driver(name="Pricing power", direction="tailwind", evidence="Guidance raised twice", source=src, confidence="high"),
            Driver(name="Customer concentration", direction="headwind", evidence="Top customer 20% of revenue", source=src, confidence="medium"),
        ],
        bull_case=[BullPoint(point="Revenue acceleration", evidence="+93% y/y", source=src, strength="strong")],
        bear_case=[BearPoint(point="Valuation", evidence="Trades at 200x forward", source=src, severity="material")],
        debate=[
            DebateRound(
                driver="Pricing power",
                bull="Guidance raised twice",
                bull_source=src,
                bear="Rival undercuts on price",
                bear_source=src,
                verdict="Bull carried it: raise came with volume growth",
                verdict_side="bull",
            )
        ],
        falsifiers=["Next quarter's revenue growth falls below 50%"],
        confidence="high",
        confidence_why="Multiple independent sources corroborate the acceleration.",
    )
    return DeepResult(
        ticker="TEST",
        name="Test Corp",
        sector="Information Technology",
        industry="Software",
        as_of="2026-08-29",
        research=research,
        thesis=thesis,
        catalysts=[Catalyst(event="Q3 earnings", window="early November", expected="Beat extends the thesis; miss breaks it", source=src)],
        llm_used=True,
        models_used=["deepseek-v4-pro:0813"],
    )


def test_render_contains_all_sections():
    md = render_markdown(make_result())
    assert "# TEST — deep qualitative dive" in md
    assert "Verdict: 🟢 CONSTRUCTIVE" in md
    assert "## Thesis" in md
    assert "## Drivers" in md
    assert "## Bull vs bear, driver by driver" in md
    assert "## Bull case" in md
    assert "## Bear case" in md
    assert "## What would change this call" in md
    assert "## Catalysts" in md
    assert "## Research base" in md
    assert "Revenue grew 93% y/y" in md


def test_render_incomplete_result_shows_findings():
    result = make_result()
    result.thesis = None
    result.error = "no drivers identified"
    md = render_markdown(result)
    assert "Dive incomplete" in md
    assert "Revenue grew 93% y/y" in md
    assert "no drivers identified" in md


def test_finding_categories_grouped():
    md = render_markdown(make_result())
    assert "### business" in md
    assert "### competition" in md


def test_sources_render_as_links():
    md = render_markdown(make_result())
    assert "[source](https://example.com/q2)" in md

def make_macro_view(available: bool = True):
    from ptm.deepsearch.models import MacroImplication, MacroView

    view = MacroView(available=available, sector="Information Technology")
    if available:
        view.bias = "NET_LONG"
        view.pmi = 52.3
        view.nmi = 53.1
        view.new_orders = 55.2
        view.tens_minus_twos = 0.42
        view.vix = 13.7
        view.sector_tilt = "long"
        view.sector_why = "mfg new orders growing: computer & electronic products"
        view.implications = [
            MacroImplication(
                channel="end-market demand",
                direction="helps",
                why="new orders expanding points to sustained enterprise IT spend",
            )
        ]
        view.narrative = "Expanding PMI supports enterprise software demand."
    else:
        view.reason = "no curated files"
    return view


def test_macro_section_renders_when_available():
    from ptm.deepsearch.render import render_macro_section

    md = render_macro_section(make_macro_view(available=True))
    assert "## Macro & ISM backdrop" in md
    assert "ISM PMI" in md and "52.3" in md
    assert "end-market demand" in md
    assert "transmits into this company" in md


def test_macro_section_renders_unavailable():
    from ptm.deepsearch.render import render_macro_section

    md = render_macro_section(make_macro_view(available=False))
    assert "Not available" in md and "no curated files" in md


def test_report_includes_macro_section():
    result = make_result()
    result.macro = make_macro_view(available=True)
    md = render_markdown(result)
    assert "## Macro & ISM backdrop" in md
    assert "transmits into this company" in md
