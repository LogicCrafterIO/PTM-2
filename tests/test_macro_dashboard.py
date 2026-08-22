from ptm.ingest.ism_sectors import compute_sector_tilts
from ptm.macro import build_dashboard
from ptm.models import Bias
from tests.conftest import write_macro_inputs


def test_spx_below_bear_level():
    write_macro_inputs(spx_last=4000.0, spx_high=5200.0)
    snap = build_dashboard()
    assert snap.in_bear is True
    assert snap.signals["regime"] == -1.0
    assert any("bear" in n.lower() for n in snap.notes)


def test_spx_above_bear_level():
    write_macro_inputs(spx_last=5000.0, spx_high=5200.0)
    snap = build_dashboard()
    assert snap.in_bear is False
    assert snap.signals["regime"] == 1.0


def test_pmi_expansion_and_new_orders_lead():
    write_macro_inputs(pmi=55.0, new_orders=56.0)
    snap = build_dashboard()
    assert snap.signals["ism_pmi"] == 1.0
    assert snap.signals["ism_new_orders"] == 1.0


def test_early_slowdown_new_orders():
    write_macro_inputs(pmi=55.0, new_orders=48.0)
    snap = build_dashboard()
    assert snap.signals["ism_pmi"] == 1.0
    assert snap.signals["ism_new_orders"] == -0.5
    assert any("early slowdown" in n.lower() for n in snap.notes)


def test_pmi_peak_zone():
    write_macro_inputs(pmi=62.0, new_orders=61.0)
    snap = build_dashboard()
    assert snap.signals["ism_pmi"] == 0.0
    assert any("peak" in n.lower() for n in snap.notes)


def test_pmi_trough_and_hard_contraction():
    write_macro_inputs(pmi=42.0, new_orders=41.0)
    snap = build_dashboard()
    assert snap.signals["ism_pmi"] == 0.3
    write_macro_inputs(pmi=38.0, new_orders=37.0)
    snap = build_dashboard()
    assert snap.signals["ism_pmi"] == -1.0


def test_curve_inverted_uses_short_rate_proxy():
    write_macro_inputs(tnx=30.0, irx=40.0, fvx=35.0)
    snap = build_dashboard()
    assert snap.tens_minus_twos == -10.0
    assert snap.curve_inverted is True
    assert snap.curve_second_leg == "irx"
    assert snap.signals["curve"] == -1.0


def test_umcsi_vix_real_rate_thresholds():
    write_macro_inputs(umcsi=49.0, vix=14.0, tnx=42.0, cpi_yoy=0.03)
    snap = build_dashboard()
    assert snap.signals["umcsi"] == -1.0
    assert snap.signals["vix"] == 0.5
    assert snap.real_10y is not None and snap.real_10y > 1.0
    assert snap.signals["real_rate"] == -0.3
    write_macro_inputs(tnx=4.2, cpi_yoy=0.03, umcsi=72.0, vix=14.0)
    snap = build_dashboard()
    assert snap.real_10y is not None
    assert abs(snap.real_10y - (4.2 - 0.03)) < 1e-9


def test_bias_thresholds():
    write_macro_inputs()
    snap = build_dashboard()
    assert snap.score > 0.30
    assert snap.bias == Bias.NET_LONG
    write_macro_inputs(
        spx_last=4000.0,
        spx_high=5200.0,
        tnx=30.0,
        irx=40.0,
        fvx=40.0,
        pmi=38.0,
        new_orders=37.0,
        nmi=38.0,
        umcsi=49.0,
        vix=30.0,
    )
    snap = build_dashboard()
    assert snap.score < -0.30
    assert snap.bias == Bias.NET_SHORT


def test_missing_inputs_neutral():
    snap = build_dashboard()
    assert snap.bias == Bias.NEUTRAL
    assert snap.score == 0.0
    assert snap.sector_tilts == []


def test_dashboard_tilts_are_deterministic():
    write_macro_inputs()
    snap = build_dashboard()
    from ptm.config import data_dir
    from ptm.io import read_json

    ism = read_json(data_dir("curated", "ism.json"))
    expected = compute_sector_tilts(ism, pmi=ism.get("pmi"))
    assert snap.sector_tilts == expected
    assert snap.llm_narrative == ""


def _permit_history(values: list[float]) -> list[dict]:
    return [{"date": f"2026-{i + 1:02d}-01", "value": v} for i, v in enumerate(values)]


def test_permits_expansion_scores_positive():
    write_macro_inputs(permits_yoy=0.09, permits_history=_permit_history([1300] * 3 + [1420] * 3))
    snap = build_dashboard()
    assert snap.signals["permits"] == 1.0
    assert snap.permits_yoy == 0.09
    assert any("permits" in n and "expanding" in n for n in snap.notes)


def test_permits_softening_scores_negative():
    write_macro_inputs(permits_yoy=-0.08, permits_history=_permit_history([1500] * 3 + [1400] * 3))
    snap = build_dashboard()
    assert snap.signals["permits"] == -0.5
    assert any("softening" in n for n in snap.notes)


def test_deep_permits_decline_is_a_recession_lead():
    write_macro_inputs(permits_yoy=-0.25, permits_history=_permit_history([1500] * 3 + [1200] * 3))
    snap = build_dashboard()
    assert snap.signals["permits"] == -1.0
    assert any("recession" in n for n in snap.notes)


def test_deep_decline_already_turning_up_reads_as_a_trough():
    """The point of a leading indicator: permits can be bottoming while the
    annual comparison is still deeply negative, and scoring that as outright
    contraction would call the turn backwards."""
    write_macro_inputs(permits_yoy=-0.25, permits_history=_permit_history([1000] * 3 + [1150] * 3))
    snap = build_dashboard()
    assert snap.signals["permits"] == 0.3
    assert snap.permits_3m3m is not None and snap.permits_3m3m > 0
    assert any("trough" in n for n in snap.notes)


def test_flat_permits_are_neutral_not_absent():
    write_macro_inputs(permits_yoy=0.01, permits_history=_permit_history([1400] * 6))
    snap = build_dashboard()
    assert snap.signals["permits"] == 0.0
    assert snap.permits_3m3m == 0.0


def test_permits_absent_adds_no_signal():
    """A missing series must not dilute the score toward zero."""
    write_macro_inputs()
    snap = build_dashboard()
    assert "permits" not in snap.signals
    assert snap.permits_yoy is None


def test_permits_trend_needs_six_months():
    write_macro_inputs(permits_yoy=0.09, permits_history=_permit_history([1400] * 4))
    snap = build_dashboard()
    assert snap.permits_3m3m is None
    assert snap.signals["permits"] == 1.0, "the yoy signal stands without the trend"
