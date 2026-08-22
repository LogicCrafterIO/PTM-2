from pathlib import Path

from ptm.config import data_dir, toml_settings
from ptm.eval import (
    audit_run,
    check_book,
    check_idea,
    check_markdown_files,
    check_window_books,
    check_worldview,
    write_audit,
)
from ptm.io import read_json, write_json

EVAL = Path(__file__).parent / "fixtures" / "eval"


def _cfg():
    return toml_settings()


def _ids(findings) -> set[str]:
    return {f.check_id for f in findings}


def test_aee_fixture_hits_core_holes():
    idea = read_json(EVAL / "short_AEE.json")
    pack = {
        "thin": False,
        "summary": "Ameren operates regulated electric utilities.",
        "business": "",
        "mda": "Item 2. Management’s Discussion and Analysis of Financial Condition and Results of Operations 43",
        "earnings_exhibit": "iso4217:USD xbrli:shares FORM 8-K CURRENT REPORT Item 9.01 Financial Statements and Exhibits.",
    }
    ids = _ids(check_idea(idea, pack, _cfg()))
    assert "quant.pe_equals_sector" in ids
    assert "quant.non_ideal" in ids
    assert "pack.item1_empty" in ids
    assert "pack.mda_short" in ids
    assert "pack.exhibit_cover_page" in ids
    assert "qual.null_despite_pack" in ids
    assert "qual.generic_kpis" in ids
    assert "cat.earnings_not_iso" in ids
    assert "cat.headline_like" in ids
    assert "template.empty_md" in ids
    assert "template.error" in ids
    assert "timing.size_zero" not in ids


def test_aca_headlines_and_catalyst_checks():
    idea = read_json(EVAL / "long_ACA.json")
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "cat.headline_like" in ids
    assert "cat.earnings_not_iso" in ids
    # timing.rscore_tautology went with the R-score itself. The fixture still
    # carries the old prm fields; the audit must simply ignore them now.
    assert "timing.rscore_tautology" not in ids
    assert "quant.non_ideal" in ids


def test_acgl_nan_peg_and_table_dump():
    idea = read_json(EVAL / "short_ACGL.json")
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "quant.peg_nan" in ids
    assert "cat.headline_like" in ids
    assert "timing.side_mismatch" not in ids
    assert "template.error" in ids


def test_acn_short_green_uptrend():
    idea = read_json(EVAL / "short_ACN.json")
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "timing.side_mismatch" not in ids
    assert "cat.earnings_not_iso" in ids


def test_tradeable_supported_idea_cannot_remain_investment_only():
    idea = {
        "candidate": {"ticker": "AGX", "side": "long"},
        "state": "investment_only",
        "qual": {"supports_outlier": True},
        "catalysts": {
            "earnings_date": "2026-09-03",
            "earnings_in_window": True,
            "tradeable": True,
            "non_earnings": [],
        },
        "extra": {"gates": []},
        "template_markdown": "# AGX",
    }
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "cat.tradeable_marked_investment_only" in ids


def test_worldview_materials_contradiction():
    snap = read_json(EVAL / "macro_snapshot.json")
    ism = {
        "errors": ["live manufacturing fetch failed; used bundled July fixture"],
        "urls": {"pmi": str(Path("tests/fixtures/ism_july_manufacturing.md"))},
        "as_of": "2026-08-16T16:00:00+00:00",
        "manufacturing": {"report_month": "July 2026"},
    }
    ids = _ids(check_worldview(ism, snap, _cfg()))
    assert "worldview.ism_fixture_fallback" in ids
    assert "sector.why_sign_mismatch" in ids
    assert "sector.industry_vs_sector_disagree" in ids
    assert "worldview.curve_label_10s5s" in ids


def test_book_empty_vs_templated():
    ideas = [read_json(EVAL / "long_ACA.json"), read_json(EVAL / "short_ACN.json")]
    book = {"ideas": [], "limit_breaches": ["only 0 names (target 8-12)"]}
    ids = _ids(check_book(book, ideas, _cfg()))
    assert "book.out_of_range" in ids
    assert "book.stale_vs_ideas" in ids


def test_thin_window_is_informational_not_a_book_error(isolate_roots):
    idea = {
        "candidate": {"ticker": "NEAR", "side": "long", "sector": "Industrials"},
        "state": "templated",
        "earnings": {"days_to_earnings": 10},
        "extra": {"gates": []},
    }
    write_json(
        data_dir("curated", "book_00-30d.json"),
        {"ideas": [idea], "limit_breaches": ["only 1 names"]},
    )

    findings = check_window_books([idea], _cfg())
    thin = [f for f in findings if f.check_id == "book.window.thin"]
    assert thin and all(f.severity == "info" for f in thin)
    assert "book.out_of_range" not in _ids(findings)


def test_window_audit_flags_stored_day_mismatch(isolate_roots):
    idea = {
        "candidate": {"ticker": "NEAR", "side": "long", "sector": "Industrials"},
        "state": "templated",
        "earnings": {"days_to_earnings": 10},
        "extra": {"gates": []},
    }
    write_json(data_dir("curated", "book_31-60d.json"), {"ideas": [idea]})

    assert "book.window.wrong_bucket" in _ids(check_window_books([idea], _cfg()))


def test_md_file_that_is_json(tmp_path, isolate_roots):
    folder = tmp_path / "ideas" / "2026-08-16"
    folder.mkdir(parents=True)
    (folder / "short_AEE.md").write_text("{ \"candidate\": {} }\n", encoding="utf-8")
    idea = read_json(EVAL / "short_AEE.json")
    ids = _ids(check_markdown_files(folder, [idea]))
    assert "template.md_is_json" in ids


def test_audit_run_writes_report():
    write_json(data_dir("curated", "ideas.json"), [read_json(EVAL / "short_AEE.json")])
    write_json(data_dir("curated", "book.json"), {"ideas": [], "limit_breaches": ["only 0 names (target 8-12)"]})
    write_json(data_dir("curated", "macro_snapshot.json"), read_json(EVAL / "macro_snapshot.json"))
    write_json(
        data_dir("curated", "ism.json"),
        {"errors": ["used bundled July fixture"], "urls": {"pmi": "tests/fixtures/x.md"}, "as_of": "2026-08-16T00:00:00+00:00"},
    )
    result = audit_run()
    assert result.findings
    path = write_audit(result)
    assert path.name == "AUDIT.md"
    assert path.read_text(encoding="utf-8").startswith("# PTM process audit")
    assert data_dir("curated", "audit.json").exists()


def test_verdict_prompt_asks_a_side_specific_question():
    """A discount short is confirmed by deterioration, not refuted by it. The
    old wording made models reject every short; measured 0% pass over 100 names."""
    import inspect

    from ptm import llm

    source = inspect.getsource(llm.qualitative)
    assert "DESERVED" in source
    assert "CONFIRMING evidence for a short" in source
    assert "evidence_for" in source and "evidence_against" in source
    # The evidence-ordering rule lives in the selectable bar, not inline.
    assert "MUST be true" in llm.VERDICT_BARS["consistent"]


def test_contradictory_verdict_is_flagged(monkeypatch):
    """Evidence for the trade, none against, yet a rejection -> flag it."""
    from ptm.llm import qualitative
    from ptm.models import Candidate, Side

    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)

    def fake_chat(system, user, **kwargs):
        if "Extract operating facts" in system:
            return {"business_in_one_line": "b", "operating_plan": "p",
                    "kpis": ["backlog"], "red_flags": [], "quotes": []}
        return {"evidence_for": ["volumes down 10%", "margins compressing"],
                "evidence_against": [], "supports_outlier": False,
                "why": "no", "denial_reason": "unclear"}

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    out = qualitative(Candidate(ticker="X", side=Side.SHORT, pe1=10.0, sector_pe1=20.0), "pack text here")
    assert out.supports_outlier is False          # the verdict stands
    assert "verdict_contradicts_evidence" in out.red_flags   # but it is visible
    assert out.evidence_for and not out.evidence_against


def test_qualitative_bar_is_selectable():
    from ptm.config import toml_settings
    from ptm.llm import VERDICT_BARS, _verdict_bar

    assert set(VERDICT_BARS) == {"consistent", "strict"}
    assert "SPECIFICITY" in VERDICT_BARS["strict"]
    assert "MUST be true" in VERDICT_BARS["consistent"]
    # Both keep the anti-contradiction rule that fixed the 0% pass rate.
    for text in VERDICT_BARS.values():
        assert "Never contradict your own evidence" in text
    assert _verdict_bar() == VERDICT_BARS[toml_settings()["llm"].get("qualitative_bar", "consistent")]
