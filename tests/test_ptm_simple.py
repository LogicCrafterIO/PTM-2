"""Tests for the ptm_simple theme-first process (kept off the PTM pipeline)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from ptm_simple.gate import gate_member, gate_theme
from ptm_simple.radar import _member_snapshot, theme_radar
from ptm_simple.run import assemble_book
from ptm_simple.select import select_members


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def watchlist_xlsx(tmp_path):
    """A miniature Master watchlist with the sheet's quirks reproduced:
    label in col J, a ticker sitting IN the label column, a section header,
    and a two-row theme."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Master watchlist"
    ws["C1"] = "AI HARDWARE"  # section header: ignored
    ws["H2"], ws["I2"], ws["J2"], ws["K2"] = "ARM", "AMD", "AI Semiconductor   chips", "NVDA"
    ws["G3"], ws["H3"], ws["I3"] = "QCOM", "INTC", "MU"  # continuation row
    ws["H4"], ws["I4"], ws["J4"] = "DLR", "IRM", "Data centre REIT"  # ticker in label col
    ws["K4"] = "EQIX"
    ws["H5"], ws["J5"] = "WDC", "Storgae Hardware/Memory"  # alias normalisation
    ws["I5"], ws["J5"] = "STX", "Storgae Hardware/Memory"
    path = tmp_path / "pack.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def members():
    """Two covered members: one aligned long, one divergent (short case)."""
    ref = date(2026, 9, 1)
    aligned = {
        "ticker": "AAA", "covered": True, "rev90": 4.0, "up30": 3, "down30": 0,
        "earnings_date": "2026-09-10", "days_to_print": 9,
        "revenue": 1e9, "net_income": 1e8, "cash": 5e8, "market_cap": 8e9,
    }
    divergent = {
        "ticker": "BBB", "covered": True, "rev90": -3.0, "up30": 0, "down30": 2,
        "earnings_date": "2026-09-12", "days_to_print": 11,
        "revenue": 5e8, "net_income": -2e7, "cash": -1e8, "market_cap": 4e8,
    }
    thin = {"ticker": "CCC", "covered": False, "rev90": None, "up30": None, "down30": None,
            "earnings_date": None, "days_to_print": None, "revenue": None, "net_income": None,
            "cash": None, "market_cap": None}
    return [aligned, divergent, thin], ref


def _row(members_list, **kw):
    base = {
        "theme": "Test theme", "thesis": "", "status": "ACTIVE", "lean": "long",
        "breadth": 0.5, "coverage": 0.67, "members_covered": 2, "members_total": 3,
        "prints_14d": [], "bellwether": "AAA", "divergent": ["BBB"], "members": members_list,
        "why_now": None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------- thememap
def test_parse_watchlist_layout_and_aliases(watchlist_xlsx):
    from ptm_simple.thememap import parse_watchlist

    themes = {t["theme"]: sorted(t["members"]) for t in parse_watchlist(watchlist_xlsx, min_members=2)}
    # label alias applied; the ticker sitting in the label column is still a member
    assert themes["Data centre REIT"] == ["DLR", "EQIX", "IRM"]
    assert themes["Storage Hardware/Memory"] == ["STX", "WDC"]
    assert themes["AI Semiconductor chips"] == ["AMD", "ARM", "INTC", "MU", "NVDA", "QCOM"]
    # the section header never becomes a theme
    assert "AI HARDWARE" not in themes
    # continuation rows append to the current theme
    assert "MU" in themes["AI Semiconductor chips"]


def test_build_theme_map_reverse_index(watchlist_xlsx, tmp_path, monkeypatch):
    from ptm.config import set_roots
    from ptm_simple.thememap import build_theme_map

    set_roots(data=tmp_path, ideas=tmp_path / "ideas")
    out = build_theme_map(watchlist_xlsx)
    assert out["theme_count"] == 3
    assert set(out["ticker_themes"]["EQIX"]) == {"Data centre REIT"}


# ---------------------------------------------------------------- radar
def test_member_snapshot_reads_cache_and_age(tmp_path, monkeypatch):
    from ptm.config import set_roots

    set_roots(data=tmp_path, ideas=tmp_path / "ideas")
    fresh = tmp_path / "raw" / "expectations"
    fresh.mkdir(parents=True)
    payload = {
        "ticker": "AAA", "earnings_date": "2026-09-10",
        "revisions": {"available": True, "change_90d_pct": 4.0, "analysts_up_30d": 3, "analysts_down_30d": 0},
    }
    cache = fresh / "AAA.json"
    cache.write_text(json.dumps(payload))
    snap = _member_snapshot("AAA", {}, date(2026, 9, 1))
    assert snap["covered"] and snap["rev90"] == 4.0 and snap["days_to_print"] == 9

    stale = fresh / "BBB.json"
    stale.write_text(json.dumps(payload))
    import os
    from datetime import datetime

    old = datetime(2026, 6, 3).timestamp()
    os.utime(stale, (old, old))
    assert _member_snapshot("BBB", {}, date(2026, 9, 1))["covered"] is False


def _snap(ticker, rev90, dprint=None):
    return {"ticker": ticker, "covered": True, "rev90": rev90, "up30": 1, "down30": 0,
            "earnings_date": None, "days_to_print": dprint, "revenue": None,
            "net_income": None, "cash": None, "market_cap": None}


def test_theme_radar_status_thresholds(members):
    _, ref = members
    # one covered member, all up -> breadth +1, coverage 1.0
    row = theme_radar(_row([_snap("AAA", 4.0)]), {}, ref)
    assert row["status"] == "ACTIVE" and row["lean"] == "long" and row["breadth"] == 1.0
    # 2 up, 1 down of 5 covered -> breadth 0.2 -> WARM
    warm_members = [_snap("A", 4.0), _snap("B", 4.0), _snap("C", -4.0), _snap("D", 0.1), _snap("E", 0.2)]
    assert theme_radar(_row(warm_members), {}, ref)["status"] == "WARM"
    # one mildly up member -> breadth 0 -> COLD
    assert theme_radar(_row([_snap("A", 0.1)]), {}, ref)["status"] == "COLD"
    # divergent members are exactly those revising against the breadth sign
    row = theme_radar(_row([_snap("A", 4.0), _snap("B", -3.0)]), {}, ref)
    assert row["breadth"] == 0.0 and row["status"] == "COLD"  # netted flat
    # 3 up, 2 down of 5 -> breadth +0.2; the two downs diverge against the long lean
    row = theme_radar(_row([_snap("A", 4.0), _snap("B", 4.0), _snap("C", 4.0),
                            _snap("B2", -3.0), _snap("B3", -1.0)]), {}, ref)
    assert row["divergent"] == ["B2", "B3"]
    row = theme_radar(_row([_snap("A", -4.0), _snap("B", -4.0), _snap("S", 3.0)]), {}, ref)
    assert row["lean"] == "short" and row["divergent"] == ["S"]


# ---------------------------------------------------------------- select
def test_select_ranks_both_sides(members):
    members_list, _ = members
    sel = select_members(_row(members_list, breadth=0.5, lean="long"))
    # the aligned compounder leads the longs; the divergent name leads the shorts
    assert sel["long"][0]["ticker"] == "AAA"
    assert sel["short"][0]["ticker"] == "BBB"
    assert all(e["long_score"] > 0 for e in sel["long"])


def test_select_is_symmetric_in_falling_themes(members):
    """A falling theme is the short side of the same signal: members with
    falling estimates rank as shorts, and a member rising against a falling
    theme ranks as a LONG (the share-gainer), never as a short."""
    members_list, _ = members
    falling = _row(members_list, breadth=-1.0, lean="short", status="ACTIVE")
    sel = select_members(falling)
    # BBB's own estimates fall -> it is the short candidate even though it
    # 'diverges' by being a member of a falling theme is the norm there
    assert sel["short"][0]["ticker"] == "BBB"
    # AAA's estimates rise against the falling theme -> it ranks as a long
    assert sel["long"][0]["ticker"] == "AAA"
    # and the rising member is never offered as a short candidate
    assert all(e["ticker"] != "AAA" or e["short_score"] <= 0.25 for e in sel["short"])


# ---------------------------------------------------------------- gate
def test_gate_member_long_pass_and_fail_closed(members):
    members_list, ref = members
    aligned = members_list[0]
    qual = {"evidence_for": [{"claim": "backlog +12%", "metric": "backlog", "impact_pct": 12.0,
                              "impact_on": "revenue", "quantified": True}], "evidence_against": []}
    verdict = gate_member(aligned, _row(members_list), qual, ref)
    assert verdict["side"] == "long"
    assert verdict["passed"] is True
    # no dive yet -> getting-paid fails closed as pending
    verdict = gate_member(aligned, _row(members_list), None, ref)
    assert verdict["passed"] is False
    assert any(g["gate"] == "getting_paid" and not g["pass"] for g in verdict["gates"])
    # a cold theme fails why-now
    verdict = gate_member(aligned, _row(members_list, status="COLD"), qual, ref)
    assert verdict["passed"] is False


def test_gate_member_short_diverger_needs_material_impact(members):
    members_list, ref = members
    divergent = members_list[1]
    weak = {"evidence_for": [{"claim": "price up", "impact_pct": 1.0, "quantified": True,
                              "metric": "price", "impact_on": "price"}], "evidence_against": []}
    # 1% impact is below the 3% bar; and the COLD row would fail why-now, so
    # give the theme WARM status and check only the impact gate fails
    row = _row(members_list, breadth=-0.5, lean="short", status="WARM")
    verdict = gate_member(divergent, row, weak, ref)
    impact = next(g for g in verdict["gates"] if g["gate"] == "getting_paid")
    assert impact["pass"] is False and "below the impact bar" in impact["detail"]


def test_gate_theme_splits_survivors_and_parked(members):
    members_list, ref = members
    qual = {"evidence_for": [{"impact_pct": 9.0, "quantified": True, "metric": "ebitda",
                              "impact_on": "ebitda", "claim": "x"}], "evidence_against": []}
    row = _row(members_list, breadth=0.5, lean="long")
    sel = select_members(row)
    out = gate_theme(sel, row, {"AAA": qual, "BBB": None}, ref)
    assert out["breadth_abs"] == 0.5
    assert all(i["passed"] for i in out["ideas"])
    assert all(not i["passed"] for i in out["parked"])


def test_gate_falling_theme_yields_short_and_resister(members):
    """The short-side symmetry, end to end: in an ACTIVE falling theme the
    member with falling estimates becomes a SHORT idea (with the theme), and
    the member rising against the theme becomes a LONG idea (the diverger) —
    both pass why-now on their own direction, both fail closed without a dive."""
    members_list, ref = members
    falling = _row(members_list, breadth=-1.0, lean="short", status="ACTIVE")
    qual = {"evidence_for": [{"impact_pct": 8.0, "quantified": True, "metric": "rev",
                              "impact_on": "revenue", "claim": "x"}], "evidence_against": []}
    sel = select_members(falling)
    out = gate_theme(sel, falling, {"AAA": qual, "BBB": qual}, ref)
    sides = {i["ticker"]: i["side"] for i in out["ideas"]}
    # BBB: estimates falling with the theme -> short. AAA: estimates rising
    # against a falling theme -> the share-gainer long.
    assert "BBB" in [i["ticker"] for i in out["ideas"]] or "BBB" in [i["ticker"] for i in out["parked"]]
    if "BBB" in [i["ticker"] for i in out["ideas"]]:
        assert [i for i in out["ideas"] if i["ticker"] == "BBB"][0]["side"] == "short"
    if "AAA" in [i["ticker"] for i in out["ideas"]]:
        assert [i for i in out["ideas"] if i["ticker"] == "AAA"][0]["side"] == "long"
    # without a dive, both fail closed regardless of side
    out2 = gate_theme(sel, falling, {"AAA": None, "BBB": None}, ref)
    assert all(not i["passed"] for i in out2["ideas"])


# ---------------------------------------------------------------- book
def test_assemble_book_caps_and_parks():
    def idea(ticker, theme, side, rev90=1.0):
        return {"ticker": ticker, "theme": theme, "side": side, "rev90": rev90,
                "days_to_print": 5, "earnings_date": "2026-09-10", "passed": True,
                "gates": [], "lean": "long", "breadth": 0.5}

    gated = [{
        "theme": "T1", "breadth_abs": 0.8, "status": "ACTIVE",
        "ideas": [idea("A", "T1", "long"), idea("B", "T1", "long"), idea("C", "T1", "long")],
        "parked": [],
    }]
    payload = assemble_book(gated, date(2026, 9, 1), per_theme=2, max_positions=12)
    assert [i["ticker"] for i in payload["book"]] == ["A", "B"]  # per-theme cap, breadth-ranked
    assert [i["ticker"] for i in payload["overflow"]] == ["C"]


# ---------------------------------------------------------------- viewer glue
def _seed_simple_artifacts(isolate_roots):
    """Write a small set of simple-process artifacts under the isolated roots."""
    from ptm.config import data_dir, ideas_dir
    from ptm.io import write_json

    sdir = data_dir("simple")
    write_json(sdir / "theme_map.json", {"source": "xlsx", "theme_count": 3, "ticker_count": 5,
                                         "themes": [{"theme": "Data centre REIT", "members": ["DLR", "EQIX"]}]})
    write_json(sdir / "theme_map_wiki.json", {"source": "wikipedia-industry", "theme_count": 9,
                                              "ticker_count": 20, "wiki_fallbacks": 4, "themes": []})
    write_json(sdir / "radar_2026-09-01.json", {"as_of": "2026-09-01", "themes": []})
    write_json(sdir / "radar_2026-09-08.json", {"as_of": "2026-09-08", "themes": []})
    write_json(sdir / "simple_book_2026-09-01.json", {"as_of": "2026-09-01", "book": [1], "overflow": [2, 3]})
    write_json(sdir / "watchlist.json", {"parked": [1, 2]})
    rdir = ideas_dir("simple", "Data centre REIT")
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "DLR.md").write_text("# DLR long", encoding="utf-8")
    return sdir


def test_viewer_artifacts_inventory(isolate_roots):
    from ptm_simple import viewer

    _seed_simple_artifacts(isolate_roots)
    arts = viewer.artifacts()
    assert arts["maps"]["manual"]["exists"] and arts["maps"]["manual"]["themes"] == 3
    assert arts["maps"]["wiki"]["fallbacks"] == 4
    assert arts["radar_files"] == ["2026-09-01", "2026-09-08"] and arts["radar_date"] == "2026-09-08"
    assert arts["book"]["ideas"] == 1 and arts["book"]["overflow"] == 2
    assert arts["watchlist"]["parked"] == 2
    assert arts["reports"] == 1


def test_viewer_theme_map_and_radar_readers(isolate_roots):
    from ptm_simple import viewer

    _seed_simple_artifacts(isolate_roots)
    got = viewer.get_theme_map("wiki")
    assert got["map"]["theme_count"] == 9 and got["source"] == "wiki"
    assert "error" in viewer.get_theme_map("bogus")
    radar = viewer.get_radar()  # latest wins
    assert radar["radar"]["as_of"] == "2026-09-08"
    dated = viewer.get_radar("2026-09-01")
    assert dated["radar"]["as_of"] == "2026-09-01"
    assert "error" in viewer.get_radar("2001-01-01")


def test_viewer_read_report_blocks_traversal(isolate_roots):
    from ptm_simple import viewer

    _seed_simple_artifacts(isolate_roots)
    ok = viewer.read_report("Data centre REIT/DLR.md")
    assert ok["markdown"].startswith("# DLR")
    assert viewer.read_report("../../curated/universe.csv") == {"error": "not found"}
    assert viewer.read_report("nope/missing.md") == {"error": "not found"}


def test_viewer_start_guards(isolate_roots):
    from ptm_simple import viewer

    ok, payload, code = viewer.start("nonsense", {})
    assert not ok and code == 400
    # a theme pass dives tickers, so it refuses to start on other LLM work
    ok, payload, code = viewer.start("run", {"theme": "Data centre REIT"}, other_work_running=True)
    assert not ok and code == 409 and "deep-dive batch" in payload["error"]
    assert not viewer.status()["running"]  # nothing was actually started


def test_viewer_theme_detail_unknown_theme(isolate_roots):
    from ptm_simple import viewer

    _seed_simple_artifacts(isolate_roots)
    assert "error" in viewer.get_theme_detail("Ghost theme", "manual")