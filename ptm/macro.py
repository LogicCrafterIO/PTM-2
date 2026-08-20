from __future__ import annotations

from datetime import datetime, timezone

from ptm.config import data_dir, toml_settings
from ptm.formulas import bear_level
from ptm.ingest.ism_sectors import compute_sector_tilts
from ptm.io import read_json, write_json
from ptm.models import Bias, MacroSnapshot


def _last(history: list[dict]) -> float | None:
    if not history:
        return None
    return float(history[-1]["close"])


def _max(history: list[dict]) -> float | None:
    if not history:
        return None
    return max(float(row["close"]) for row in history)


def _closes(history: list[dict]) -> list[float]:
    return [float(row["close"]) for row in history]


def _yoy_from_points(history: list[dict], key: str = "close") -> float | None:
    if len(history) < 252:
        return None
    now = float(history[-1][key])
    prev = float(history[-252][key])
    if prev == 0:
        return None
    return now / prev - 1.0


def _three_month_trend(history: list[dict]) -> float | None:
    """The last three months against the prior three.

    Monthly permits are volatile enough that a single print says little - a wet
    March or a pulled-forward December moves the number several percent - so the
    standard read smooths both ends. This also turns before the year-over-year
    comparison does, which is the whole point of a leading indicator: a series
    can be bottoming while its annual change is still deeply negative.
    """
    values = [float(row["value"]) for row in history or [] if row.get("value") is not None]
    if len(values) < 6:
        return None
    recent = sum(values[-3:]) / 3.0
    prior = sum(values[-6:-3]) / 3.0
    if prior == 0:
        return None
    return recent / prior - 1.0


def build_dashboard() -> MacroSnapshot:
    cfg = toml_settings()
    macro_cfg = cfg["macro"]
    yf = {}
    fred = {}
    ism = {}
    yf_path = data_dir("curated", "macro_yfinance.json")
    fred_path = data_dir("curated", "macro_fred.json")
    ism_path = data_dir("curated", "ism.json")
    if yf_path.exists():
        yf = read_json(yf_path).get("series", {})
    if fred_path.exists():
        fred = read_json(fred_path).get("series", {})
    if ism_path.exists():
        ism = read_json(ism_path)

    spx_hist = yf.get("spx", {}).get("history") or []
    spx_last = _last(spx_hist)
    high = _max(spx_hist)
    bear = bear_level(high, macro_cfg["bear_drawdown"]) if high else None
    in_bear = bool(spx_last is not None and bear is not None and spx_last < bear)

    tnx = yf.get("tnx", {}).get("last")
    irx = yf.get("irx", {}).get("last")
    fvx = yf.get("fvx", {}).get("last")
    # ^IRX is the 13-week bill (short-rate proxy for 2s). Yahoo has no clean 2y index.
    short_leg = irx if irx is not None else fvx
    curve_second_leg = "irx" if irx is not None else ("fvx" if fvx is not None else "")
    tens_twos = None
    if tnx is not None and short_leg is not None:
        tens_twos = float(tnx) - float(short_leg)
    inverted = tens_twos is not None and tens_twos <= macro_cfg["curve_invert"]

    cpi_yoy = (fred.get("cpi") or {}).get("yoy")
    real_10y = None
    if tnx is not None and cpi_yoy is not None:
        real_10y = float(tnx) / 10.0 - float(cpi_yoy) if float(tnx) > 20 else float(tnx) - float(cpi_yoy)

    pmi = ism.get("pmi") or (fred.get("ism_pmi") or {}).get("last")
    nmi = ism.get("nmi") or (fred.get("ism_nmi") or {}).get("last")
    new_orders = ((ism.get("manufacturing") or {}).get("components") or {}).get("new_orders") or {}
    new_orders_val = new_orders.get("value") if isinstance(new_orders, dict) else None
    umcsi = (fred.get("umcsent") or {}).get("last")
    permits = fred.get("permits") or {}
    permits_yoy = permits.get("yoy")
    permits_3m3m = _three_month_trend(permits.get("history") or [])
    m2_yoy = (fred.get("m2") or {}).get("yoy")
    vix = yf.get("vix", {}).get("last")

    signals: dict[str, float] = {}
    notes: list[str] = []

    if in_bear:
        signals["regime"] = -1.0
        notes.append("S&P below 20% bear level")
    elif spx_last is not None and bear is not None:
        signals["regime"] = 1.0
        notes.append("S&P above bear level (pro bull definition)")

    if inverted:
        signals["curve"] = -1.0
        notes.append("yield curve inverted (10s minus 13-week bill proxy for 2s)")
    elif tens_twos is not None and tens_twos > 0:
        signals["curve"] = 0.5

    if pmi is not None:
        if pmi >= macro_cfg["ism_peak"]:
            signals["ism_pmi"] = 0.0
            notes.append(f"ISM PMI {pmi} in peak zone → growth slowing")
        elif pmi < macro_cfg["ism_expansion"]:
            if macro_cfg["ism_trough_low"] <= pmi <= macro_cfg["ism_trough_high"]:
                signals["ism_pmi"] = 0.3
                notes.append(f"ISM PMI {pmi} trough zone")
            else:
                signals["ism_pmi"] = -1.0
                notes.append(f"ISM PMI {pmi} contraction")
        else:
            signals["ism_pmi"] = 1.0
            notes.append(f"ISM PMI {pmi} expansion")

    if new_orders_val is not None:
        if pmi is not None and pmi >= macro_cfg["ism_expansion"] and new_orders_val < macro_cfg["ism_expansion"]:
            signals["ism_new_orders"] = -0.5
            notes.append(f"New Orders {new_orders_val} below 50 while PMI expanding (early slowdown)")
        elif new_orders_val >= macro_cfg["ism_expansion"]:
            signals["ism_new_orders"] = 1.0
            notes.append(f"ISM New Orders {new_orders_val} expansion (leads PMI)")
        else:
            signals["ism_new_orders"] = -1.0
            notes.append(f"ISM New Orders {new_orders_val} contraction")

    if nmi is not None:
        if nmi >= macro_cfg["ism_peak"]:
            signals["ism_nmi"] = 0.0
        elif nmi < macro_cfg["ism_expansion"]:
            signals["ism_nmi"] = -1.0
        else:
            signals["ism_nmi"] = 1.0

    if umcsi is not None:
        if umcsi > macro_cfg["umcsi_bull"]:
            signals["umcsi"] = 1.0
        elif umcsi < macro_cfg["umcsi_benign_low"]:
            signals["umcsi"] = -1.0
        else:
            signals["umcsi"] = 0.0

    # Building permits lead the cycle by roughly six to twelve months - housing
    # turns before employment and capex do, which is why the Conference Board
    # carries it in the LEI. Scored on the annual change, with the 3m/3m read
    # breaking the tie when a deep decline is already bottoming: reading the
    # trough as outright contraction is the error this indicator exists to avoid.
    if permits_yoy is not None:
        pct = permits_yoy * 100
        trend = "" if permits_3m3m is None else f", 3m/3m {permits_3m3m * 100:+.1f}%"
        if permits_yoy >= macro_cfg["permits_strong"]:
            signals["permits"] = 1.0
            notes.append(f"building permits {pct:+.1f}% yoy{trend} — housing expanding, leads the cycle")
        elif permits_yoy <= macro_cfg["permits_recession"]:
            if permits_3m3m is not None and permits_3m3m > 0:
                signals["permits"] = 0.3
                notes.append(
                    f"building permits {pct:+.1f}% yoy{trend} — deep annual decline but turning up "
                    "over the last quarter (trough)"
                )
            else:
                signals["permits"] = -1.0
                notes.append(
                    f"building permits {pct:+.1f}% yoy{trend} — decline of a size that has led "
                    "past recessions"
                )
        elif permits_yoy <= macro_cfg["permits_weak"]:
            signals["permits"] = -0.5
            notes.append(f"building permits {pct:+.1f}% yoy{trend} — housing softening")
        else:
            signals["permits"] = 0.0
            notes.append(f"building permits {pct:+.1f}% yoy{trend} — flat")

    if real_10y is not None:
        signals["real_rate"] = 1.0 if real_10y < macro_cfg["real_rate_cheap"] else -0.3

    if vix is not None:
        signals["vix"] = -1.0 if vix >= 25 else (0.5 if vix < 18 else 0.0)

    score = sum(signals.values()) / len(signals) if signals else 0.0
    if score > macro_cfg["bias_long_threshold"]:
        bias = Bias.NET_LONG
    elif score < macro_cfg["bias_short_threshold"]:
        bias = Bias.NET_SHORT
    else:
        bias = Bias.NEUTRAL

    snap = MacroSnapshot(
        as_of=datetime.now(timezone.utc).isoformat(),
        spx_last=spx_last,
        bear_level=bear,
        in_bear=in_bear,
        tens_minus_twos=tens_twos,
        curve_inverted=inverted,
        curve_second_leg=curve_second_leg,
        real_10y=real_10y,
        vix=vix,
        ism_pmi=pmi,
        ism_nmi=nmi,
        umcsi=umcsi,
        m2_yoy=m2_yoy,
        permits_yoy=permits_yoy,
        permits_3m3m=permits_3m3m,
        signals=signals,
        score=round(score, 4),
        bias=bias,
        notes=notes,
        ism_new_orders=new_orders_val,
        sector_tilts=compute_sector_tilts(ism, pmi=pmi),
    )
    write_json(data_dir("curated", "macro_snapshot.json"), snap.model_dump())
    return snap
