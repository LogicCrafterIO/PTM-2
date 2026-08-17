from pathlib import Path

from ptm.config import data_dir, toml_settings
from ptm.eval import (
    audit_run,
    check_book,
    check_idea,
    check_markdown_files,
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
    assert "timing.size_zero" in ids


def test_aca_headlines_and_rscore():
    idea = read_json(EVAL / "long_ACA.json")
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "cat.headline_like" in ids
    assert "cat.earnings_not_iso" in ids
    assert "timing.rscore_tautology" in ids
    assert "quant.non_ideal" in ids


def test_acgl_nan_peg_and_table_dump():
    idea = read_json(EVAL / "short_ACGL.json")
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "quant.peg_nan" in ids
    assert "cat.headline_like" in ids
    assert "timing.side_mismatch" in ids
    assert "template.error" in ids


def test_acn_short_green_uptrend():
    idea = read_json(EVAL / "short_ACN.json")
    ids = _ids(check_idea(idea, None, _cfg()))
    assert "timing.side_mismatch" in ids
    assert "cat.earnings_not_iso" in ids


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
