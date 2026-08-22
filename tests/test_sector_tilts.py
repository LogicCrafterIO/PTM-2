from pathlib import Path

from ptm.config import toml_settings
from ptm.ingest.ism import parse_ism_report
from ptm.ingest.ism_sectors import apply_ism_tilts, compute_sector_tilts, gics_for_ism, split_quota
from ptm.models import Candidate, Side

FIXTURES = Path(__file__).parent / "fixtures"


def _july_ism() -> dict:
    mfg = parse_ism_report((FIXTURES / "ism_july_manufacturing.md").read_text(encoding="utf-8"), "pmi")
    svc = parse_ism_report((FIXTURES / "ism_july_services.md").read_text(encoding="utf-8"), "services")
    return {"pmi": 55.6, "manufacturing": mfg, "services": svc}


def _chem_ism() -> dict:
    return {
        "pmi": 55.6,
        "manufacturing": {
            "industries": {"growth": ["Printing & Related Support Activities"], "contraction": ["Chemical Products"]},
            "new_orders_industries": {"growth": [], "contraction": ["Chemical Products"]},
            "comments": [],
        },
        "services": {"industries": {"growth": [], "contraction": []}, "new_orders_industries": {"growth": [], "contraction": []}, "comments": []},
    }


def test_unmapped_industry_does_not_crash():
    ism = {
        "pmi": 50.0,
        "manufacturing": {
            "industries": {"growth": ["Totally Fake Widgets"], "contraction": []},
            "new_orders_industries": {"growth": [], "contraction": []},
            "comments": [],
        },
        "services": {"industries": {"growth": [], "contraction": []}, "comments": []},
    }
    tilts = compute_sector_tilts(ism, pmi=50.0)
    assert isinstance(tilts, list)
    assert gics_for_ism("Totally Fake Widgets") is None


def test_chemicals_industry_row_is_short():
    tilts = compute_sector_tilts(_chem_ism(), pmi=55.6)
    chem = next(row for row in tilts if row.get("industry") == "Chemical Products")
    assert chem["tilt"] == "short"
    assert chem["score"] < 0
    assert chem["sector"] == "Materials"


def test_materials_sector_not_long_when_only_chem_contracts():
    tilts = compute_sector_tilts(_july_ism(), pmi=55.6)
    materials = next(row for row in tilts if row.get("sector") == "Materials" and not row.get("industry"))
    assert materials["tilt"] != "long"


def test_why_text_does_not_contradict_tilt_sign():
    tilts = compute_sector_tilts(_july_ism(), pmi=55.6)
    for row in tilts:
        if row.get("industry"):
            continue
        why = str(row.get("why") or "").lower()
        if "contraction" in why:
            assert row.get("tilt") != "long", row


def test_apply_tilts_specialty_chemicals_short_outranks_long():
    tilts = compute_sector_tilts(_chem_ism(), pmi=55.6)
    short = Candidate(ticker="DOW", side=Side.SHORT, sector="Materials", industry="Specialty Chemicals")
    long = Candidate(ticker="LIN", side=Side.LONG, sector="Materials", industry="Specialty Chemicals")
    apply_ism_tilts([short, long], tilts)
    assert short.ism_score > long.ism_score


def test_quota_prefers_ism_aligned_longs():
    aligned = Candidate(ticker="GOOD", side=Side.LONG, mcap_ok=True, eg1=0.1, ism_score=1.5)
    against = Candidate(ticker="BAD", side=Side.LONG, mcap_ok=True, eg1=0.1, ism_score=-1.5)
    shorts = [
        Candidate(ticker="S1", side=Side.SHORT, mcap_ok=True, eg1=-0.2, ism_score=0.5),
        Candidate(ticker="S2", side=Side.SHORT, mcap_ok=True, eg1=-0.1, ism_score=0.4),
    ]
    chosen = split_quota([aligned, against, *shorts], 4)
    long_names = [c.ticker for c in chosen if c.side == Side.LONG]
    assert long_names[0] == "GOOD"


def test_healthcare_not_skipped_in_v1():
    cfg = toml_settings()["filters"]
    assert cfg.get("skip_healthcare_v1") is False
    assert "Health Care" in (cfg.get("exclude_sectors") or [])


def test_short_industry_blocks_parent_sector_long():
    tilts = compute_sector_tilts(_july_ism(), pmi=55.6)
    disc = next(row for row in tilts if row.get("sector") == "Consumer Discretionary" and not row.get("industry"))
    industrials = next(row for row in tilts if row.get("sector") == "Industrials" and not row.get("industry"))
    assert disc["tilt"] != "long"
    assert industrials["tilt"] != "long"
    textile = next(row for row in tilts if row.get("industry") == "Textile Mills")
    other = next(row for row in tilts if row.get("industry") == "Other Services")
    assert textile["tilt"] == "short"
    assert other["tilt"] == "short"
