from __future__ import annotations

from ptm.config import toml_settings
from ptm.models import Candidate, PRMResult, Side, TimingLight, TradeIdea


def mcap_check(side: Side, market_cap: float | None) -> tuple[bool, str]:
    cfg = toml_settings()["filters"]
    if market_cap is None:
        return False, "missing market cap"
    if side == Side.LONG:
        lo, hi = cfg["long_mcap_min"], cfg["long_mcap_max"]
        if not (lo <= market_cap <= hi):
            return False, f"long mcap {market_cap:.0f} outside {lo:.0f}-{hi:.0f}"
    else:
        if market_cap < cfg["short_mcap_min"]:
            return False, f"short mcap {market_cap:.0f} below {cfg['short_mcap_min']:.0f}"
    return True, ""


def apply_process_gates(idea: TradeIdea) -> list[str]:
    """Psychology encoded as hard blocks, not coaching."""
    cfg = toml_settings()["prm"]
    blocks: list[str] = []
    if idea.qual is not None and idea.qual.supports_outlier is False:
        blocks.append("qualitative denies quant outlier")
    if idea.catalysts is not None and not idea.catalysts.tradeable:
        blocks.append("no dated 20-60d catalysts (investment idea only)")
    if idea.timing is not None and idea.timing.light == TimingLight.RED:
        blocks.append("timing red: do not enter")
    if idea.prm is not None:
        if idea.prm.blocked:
            blocks.append(idea.prm.block_reason or "PRM blocked")
        if idea.prm.r_score is not None and idea.prm.r_score < cfg["min_r_score"]:
            blocks.append(f"R-score {idea.prm.r_score:.2f} below {cfg['min_r_score']}")
    return blocks


def size_fraction(idea: TradeIdea) -> float:
    cfg = toml_settings()["prm"]
    if idea.timing and idea.timing.light == TimingLight.AMBER:
        return float(cfg["amber_size"])
    if idea.timing and idea.timing.light == TimingLight.RED:
        return 0.0
    return 1.0


def candidate_warnings(c: Candidate) -> list[str]:
    warns = list(c.warnings)
    if c.eg1 is not None and abs(c.eg1) > 2:
        warns.append("law of small numbers: |EG1| > 200%")
    if c.eg1 is not None and c.eg1 <= 0 and c.side == Side.LONG:
        warns.append("long with non-positive EG1")
    if c.peg1 is None and c.side == Side.LONG:
        warns.append("PEG1 undefined")
    return warns
