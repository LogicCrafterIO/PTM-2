from __future__ import annotations

import math

import pandas as pd

from ptm.config import data_dir, toml_settings
from ptm.formulas import earnings_growth, pe, peg, relative_peg
from ptm.gates import mcap_check
from ptm.io import write_df
from ptm.log import log
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





def _require_consensus() -> bool:
    """Whether a name must have analyst consensus to be screenable.

    Only meaningful on a live run with estimates enabled. A backdated run refuses
    consensus outright, so requiring it would empty the screen.
    """
    from ptm.asof import is_backdated
    from ptm.ingest.estimates import enabled as estimates_enabled

    if is_backdated() or not estimates_enabled():
        return False
    cfg = toml_settings().get("estimates") or {}
    return bool(cfg.get("require_consensus", True))


# Distinguishing "accelerating" from "stable" needs eg2 to be an INDEPENDENT
# second-year estimate. Without consensus it is derived as eps1 x (1 + g) using
# the same g that produced eps1, so eg2 equals eg1 to ~1e-16 and the comparison
# collapses to floating-point noise: 19 names were labelled acceleration and 8
# worsening purely on rounding. Comparisons are made against a tolerance so that
# noise cannot masquerade as a trend. See docs/EG-CASES.md.
EG_TOLERANCE = 0.005  # 0.5 percentage points of growth


def _higher(a: float, b: float) -> bool:
    """a is meaningfully above b."""
    return a > b + EG_TOLERANCE


def _lower(a: float, b: float) -> bool:
    return a < b - EG_TOLERANCE


# Cases that fit none of the process's long/short patterns. A name here is not
# a trade the process recognises, whatever its multiple looks like.
NON_IDEAL_CASES = {"long_non_ideal", "short_non_ideal", "unknown"}


def classify_long_case(eg1: float | None, eg2: float | None, sector_eg: float | None) -> str:
    if eg1 is None:
        return "unknown"
    sector = sector_eg if sector_eg is not None else 0.0
    eg2 = eg2 if eg2 is not None else eg1
    if eg1 > sector and eg2 > sector and _higher(eg2, eg1):
        return "long_case_1_acceleration"
    if eg1 > sector and abs(eg2 - eg1) < 0.05 and eg2 > sector:
        return "long_case_2_stable_above"
    if eg1 > sector and _lower(eg2, eg1) and eg2 > sector:
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
    if eg1 < 0 and _lower(eg2, eg1):
        return "short_case_1_worsening"
    if eg1 < 0 and eg2 < 0 and _higher(eg2, eg1):
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
        # Consensus supplies eps2 and both growth rates independently. Only fall
        # back to re-applying one growth rate when it is absent, and remember
        # that when it is absent eg2 carries no information beyond eg1.
        eps2 = _num(row.get("forward_eps2"))
        est_eg1 = _num(row.get("eg1"))
        est_eg2 = _num(row.get("eg2"))
        if eps2 is None and eps1 is not None and growth is not None:
            eps2 = eps1 * (1.0 + growth)
        # Consensus growth is measured on the consensus basis (its own prior-year
        # EPS), never against EDGAR's GAAP trailing figure.
        eg1 = est_eg1 if est_eg1 is not None else earnings_growth(eps1, eps0)
        if est_eg2 is not None:
            eg2 = est_eg2
        else:
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
                # Carried through so the screen can tell which basis this row is
                # on; without it the consensus requirement silently did nothing.
                "forward_source": str(row.get("forward_source") or ""),
            }
        )
    frame = pd.DataFrame(rows)

    # A near-zero EPS produces a P/E in the hundreds that says nothing about how
    # the market values the business. Those names are excluded from the sector
    # benchmark and from candidacy rather than left to distort both.
    cfg_filters = toml_settings()["filters"]
    max_pe = float(cfg_filters.get("max_screen_pe") or 200.0)
    max_pe_multiple = float(cfg_filters.get("max_sector_pe_multiple") or 0.0)
    max_rel_peg = float(cfg_filters.get("max_relative_peg") or 0.0)
    frame["pe_implausible"] = frame["pe1"].notna() & (frame["pe1"] > max_pe)

    # A name without analyst consensus is not merely less reliable, it is on a
    # different basis: consensus EPS is adjusted and runs ~18% above GAAP
    # trailing (median forward/trailing 1.184 vs 1.000 on the fallback). Its P/E
    # is therefore computed with a smaller denominator, which both misprices the
    # name and drags the sector median that every other name is judged against.
    # Excluding it costs ~4 candidates in 210; keeping it corrupts the benchmark.
    # Backdated runs are exempt: consensus is refused there, so the whole
    # universe is on one consistent extrapolated basis.
    frame["no_consensus"] = False
    if _require_consensus():
        source = frame.get("forward_source")
        if source is not None:
            frame["no_consensus"] = source.fillna("") != "analyst_consensus"
    # The benchmark is built only from names that could themselves be screened:
    # a positive, plausible P/E. Loss-makers otherwise leak in through eg1, where
    # a shrinking loss reads as +50% "growth" and lifts the sector bar for every
    # real candidate measured against it.
    usable = frame.loc[~frame["pe_implausible"] & ~frame["no_consensus"] & frame["pe1"].notna()]

    # Median, not mean: the P/E distribution has a long right tail, and a mean
    # sits well above the typical name. Benchmarking against the mean put ~73%
    # of the universe "below sector" and skewed the book short by construction.
    frame["sector_pe1"] = frame["sector"].map(usable.groupby("sector")["pe1"].median())
    frame["sector_eg1"] = frame["sector"].map(usable.groupby("sector")["eg1"].median())
    frame["sector_pe1_mean"] = frame["sector"].map(usable.groupby("sector")["pe1"].mean())
    write_df(data_dir("curated", "quant_table.csv"), frame)

    dropped = int(frame["pe_implausible"].sum())
    if dropped:
        log(f"screen: {dropped} names excluded with P/E above {max_pe:.0f} (near-zero EPS)")
    unpriced = int(frame["no_consensus"].sum())
    if unpriced:
        log(
            f"screen: {unpriced} names excluded for having no analyst consensus "
            "(their forward EPS would be on a different basis)"
        )

    # The EG case is the process's own taxonomy of what makes a valid long or
    # short. Selecting on P/E extremity alone ignored it and handed the
    # qualitative pass names at 3-12x their sector multiple — expensive because
    # earnings collapsed, not because growth justified it. Every one was
    # correctly rejected, so the whole funnel produced an empty book. Rank the
    # P/E outliers *within* names that fit a case instead.
    frame["long_case"] = [
        classify_long_case(r.eg1, r.eg2, r.sector_eg1) for r in frame.itertuples()
    ]
    frame["short_case"] = [
        classify_short_case(r.eg1, r.eg2, r.sector_eg1) for r in frame.itertuples()
    ]
    require_case = bool(cfg_filters.get("require_eg_case", True))
    frame["relative_peg"] = [
        relative_peg(r.pe1, r.sector_pe1, r.eg1, r.sector_eg1) for r in frame.itertuples()
    ]

    if max_pe_multiple:
        rich = frame[
            ~frame["pe_implausible"]
            & ~frame["no_consensus"]
            & frame["pe1"].notna()
            & frame["sector_pe1"].notna()
            & (frame["pe1"] > max_pe_multiple * frame["sector_pe1"])
        ]
        if len(rich):
            log(
                f"screen: {len(rich)} names blocked as longs at over "
                f"{max_pe_multiple:.0f}x their sector median P/E (still in the benchmark)"
            )

    if max_rel_peg:
        unbacked = frame[
            ~frame["pe_implausible"]
            & ~frame["no_consensus"]
            & frame["relative_peg"].notna()
            & (frame["relative_peg"] > max_rel_peg)
        ]
        if len(unbacked):
            log(
                f"screen: {len(unbacked)} names blocked as longs at over {max_rel_peg:.1f}x "
                "multiple premium per unit of growth premium (still in the benchmark)"
            )

    candidates: list[Candidate] = []
    min_names = int(cfg_filters.get("min_sector_names") or 2)
    for sector, group in frame.groupby("sector"):
        if not sector:
            continue
        ranked = (
            group.loc[~group["pe_implausible"] & ~group["no_consensus"]]
            .dropna(subset=["pe1"])
            .sort_values("pe1", ascending=False)
        )
        if ranked.empty or len(ranked) < min_names:
            continue
        long_eligible = ranked[~ranked["long_case"].isin(NON_IDEAL_CASES)] if require_case else ranked
        # A relative ceiling as well as the absolute one. max_screen_pe catches a
        # near-zero EPS; this catches a real but indefensible multiple - RXO
        # reached the book at 8.7x its sector median, and no operating plan
        # justifies that. Unlike the implausible-P/E rule these names stay in the
        # sector benchmark: the valuation is real, it is just not a trade.
        if max_pe_multiple:
            long_eligible = long_eligible[
                long_eligible["sector_pe1"].isna()
                | (long_eligible["pe1"] <= max_pe_multiple * long_eligible["sector_pe1"])
            ]
        # And the same idea measured against growth rather than against nothing:
        # max_sector_pe_multiple admits a name paying 3x the sector multiple for
        # flat earnings, which is the failure two independent reviews of one
        # book both flagged. A null relative_peg passes - it means the ratio
        # could not be formed, and excluding on an absent number would silently
        # drop names the EG taxonomy is the right tool for.
        if max_rel_peg:
            long_eligible = long_eligible[
                long_eligible["relative_peg"].isna()
                | (long_eligible["relative_peg"] <= max_rel_peg)
            ]
        short_eligible = ranked[~ranked["short_case"].isin(NON_IDEAL_CASES)] if require_case else ranked
        long_pool = long_eligible.head(max(3, len(long_eligible) // 8))
        short_pool = short_eligible.tail(max(3, len(short_eligible) // 8))
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
                relative_peg=_num(row["relative_peg"]),
                eg_case=row["long_case"],
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
                relative_peg=_num(row["relative_peg"]),
                eg_case=row["short_case"],
                mcap_ok=ok,
                mcap_warning="" if ok else warn,
                warnings=[] if ok else [warn],
            )
            if cand.pe1 and cand.sector_pe1 and cand.pe1 <= cand.sector_pe1:
                candidates.append(cand)
    return candidates
