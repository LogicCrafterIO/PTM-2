from __future__ import annotations

import math

import pandas as pd

from ptm.config import data_dir, toml_settings
from ptm.formulas import earnings_growth, pe, peg
from ptm.gates import mcap_check
from ptm.io import write_df
from ptm.models import Candidate, Side


def _num(value) -> float | None:
    try:
        if value is None or (isinstance(value, float) and (pd.isna(value) or math.isnan(value) or math.isinf(value))):
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except (TypeError, ValueError):
        return None


def classify_long_case(eg1: float | None, eg2: float | None, sector_eg: float | None) -> str:
    if eg1 is None:
        return "unknown"
    sector = sector_eg if sector_eg is not None else 0.0
    eg2 = eg2 if eg2 is not None else eg1
    if eg1 > sector and eg2 > sector and eg2 > eg1:
        return "long_case_1_acceleration"
    if eg1 > sector and abs(eg2 - eg1) < 0.05 and eg2 > sector:
        return "long_case_2_stable_above"
    if eg1 > sector and eg2 < eg1 and eg2 > sector:
        return "long_case_3_decel_still_above"
    if eg1 > sector * 0.5:
        return "long_case_4_6_opportunity_cost"
    if eg1 < 0 < eg2:
        return "long_case_7_10_turnaround"
    return "long_non_ideal"


def classify_short_case(eg1: float | None, eg2: float | None, sector_eg: float | None) -> str:
    if eg1 is None:
        return "unknown"
    sector = sector_eg if sector_eg is not None else 0.0
    eg2 = eg2 if eg2 is not None else eg1
    if eg1 < 0 and eg2 < eg1:
        return "short_case_1_worsening"
    if eg1 < 0 and eg2 < 0 and eg2 > eg1:
        return "short_case_2_decel_decline"
    if eg1 >= 0 and eg2 < 0:
        return "short_case_3_4_xgrowth"
    if eg1 < 0 < eg2 and eg2 < sector:
        return "short_case_5_turnaround_or_trap"
    if eg1 < sector and eg2 < sector:
        return "short_below_sector"
    return "short_non_ideal"


def build_candidates(universe: pd.DataFrame, fundamentals: pd.DataFrame) -> list[Candidate]:
    merged = universe.merge(fundamentals, on="ticker", how="left", suffixes=("", "_yf"))
    if "name_yf" in merged.columns:
        merged["name"] = merged["name"].fillna(merged["name_yf"])
    if "sector_yf" in merged.columns:
        merged["sector"] = merged["sector"].replace("", pd.NA).fillna(merged["sector_yf"]).fillna("")
    merged["price"] = pd.to_numeric(merged.get("price"), errors="coerce")
    rows = []
    for _, row in merged.iterrows():
        price = _num(row.get("price"))
        eps1 = _num(row.get("forward_eps"))
        eps0 = _num(row.get("trailing_eps"))
        growth = _num(row.get("earnings_growth"))
        eps2 = None
        if eps1 is not None and growth is not None:
            eps2 = eps1 * (1.0 + growth)
        eg1 = earnings_growth(eps1, eps0)
        eg2 = earnings_growth(eps2, eps1) if eps2 is not None else growth
        pe1 = pe(price, eps1)
        pe2 = pe(price, eps2)
        rows.append(
            {
                "ticker": row["ticker"],
                "name": row.get("name") or row.get("name_yf") or row["ticker"],
                "sector": row.get("sector") or "",
                "industry": row.get("industry") or "",
                "price": price,
                "market_cap": _num(row.get("market_cap")),
                "eps0": eps0,
                "eps1": eps1,
                "eps2": eps2,
                "eg1": eg1,
                "eg2": eg2,
                "pe1": pe1,
                "pe2": pe2,
                "peg1": _num(peg(pe1, eg1)),
                "peg2": _num(peg(pe2, eg2)),
            }
        )
    frame = pd.DataFrame(rows)
    frame["sector_pe1"] = frame.groupby("sector")["pe1"].transform("mean")
    frame["sector_eg1"] = frame.groupby("sector")["eg1"].transform("mean")
    write_df(data_dir("curated", "quant_table.csv"), frame)

    candidates: list[Candidate] = []
    min_names = int(toml_settings()["filters"].get("min_sector_names") or 2)
    for sector, group in frame.groupby("sector"):
        if not sector:
            continue
        ranked = group.dropna(subset=["pe1"]).sort_values("pe1", ascending=False)
        if ranked.empty or len(ranked) < min_names:
            continue
        long_pool = ranked.head(max(3, len(ranked) // 8))
        short_pool = ranked.tail(max(3, len(ranked) // 8))
        for _, row in long_pool.iterrows():
            side = Side.LONG
            ok, warn = mcap_check(side, row["market_cap"])
            cand = Candidate(
                ticker=row["ticker"],
                name=row["name"],
                sector=row["sector"],
                industry=row.get("industry") or "",
                side=side,
                price=row["price"],
                market_cap=row["market_cap"],
                eps0=row["eps0"],
                eps1=row["eps1"],
                eps2=row["eps2"],
                eg1=row["eg1"],
                eg2=row["eg2"],
                pe1=_num(row["pe1"]),
                pe2=_num(row["pe2"]),
                peg1=_num(row["peg1"]),
                peg2=_num(row["peg2"]),
                sector_pe1=_num(row["sector_pe1"]),
                sector_eg1=_num(row["sector_eg1"]),
                eg_case=classify_long_case(row["eg1"], row["eg2"], row["sector_eg1"]),
                mcap_ok=ok,
                mcap_warning="" if ok else warn,
                warnings=[] if ok else [warn],
            )
            if cand.pe1 and cand.sector_pe1 and cand.pe1 >= cand.sector_pe1:
                candidates.append(cand)
        for _, row in short_pool.iterrows():
            side = Side.SHORT
            ok, warn = mcap_check(side, row["market_cap"])
            cand = Candidate(
                ticker=row["ticker"],
                name=row["name"],
                sector=row["sector"],
                industry=row.get("industry") or "",
                side=side,
                price=row["price"],
                market_cap=row["market_cap"],
                eps0=row["eps0"],
                eps1=row["eps1"],
                eps2=row["eps2"],
                eg1=row["eg1"],
                eg2=row["eg2"],
                pe1=_num(row["pe1"]),
                pe2=_num(row["pe2"]),
                peg1=_num(row["peg1"]),
                peg2=_num(row["peg2"]),
                sector_pe1=_num(row["sector_pe1"]),
                sector_eg1=_num(row["sector_eg1"]),
                eg_case=classify_short_case(row["eg1"], row["eg2"], row["sector_eg1"]),
                mcap_ok=ok,
                mcap_warning="" if ok else warn,
                warnings=[] if ok else [warn],
            )
            if cand.pe1 and cand.sector_pe1 and cand.pe1 <= cand.sector_pe1:
                candidates.append(cand)
    return candidates
