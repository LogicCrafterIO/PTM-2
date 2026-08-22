from __future__ import annotations

from ptm.config import toml_settings
from ptm.models import Candidate, Side, TradeIdea
from ptm.risk import catalyst_window


def mcap_check(side: Side, market_cap: float | None) -> tuple[bool, str]:
    """Whether a name sits in its side's size band.

    Longs keep a band because the process hunts $3-10bn names specifically.
    Shorts have no floor by default (`short_mcap_min = 0`). That is not a
    loosened cap but a removed one: mcap_ok is the FIRST ranking key, so a floor
    demoted every sub-floor short beneath every large cap whatever its idea
    quality, and with 3 of 23 ready shorts clearing $20bn it capped the short
    side at 4 names on every run. Set short_mcap_min above 0 to restore it.
    """
    cfg = toml_settings()["filters"]
    if side == Side.LONG:
        if market_cap is None:
            return False, "missing market cap"
        lo, hi = cfg["long_mcap_min"], cfg["long_mcap_max"]
        if not (lo <= market_cap <= hi):
            return False, f"long mcap {market_cap:.0f} outside {lo:.0f}-{hi:.0f}"
        return True, ""
    floor = float(cfg.get("short_mcap_min") or 0)
    if floor <= 0:
        # No floor configured, so an unknown market cap is not a demotion
        # either - there is no band left for it to fall outside of.
        return True, ""
    if market_cap is None:
        return False, "missing market cap"
    if market_cap < floor:
        return False, f"short mcap {market_cap:.0f} below {floor:.0f}"
    return True, ""


def apply_process_gates(idea: TradeIdea) -> list[str]:
    """Psychology encoded as hard blocks, not coaching. No technical-analysis gates."""
    blocks: list[str] = []
    if idea.qual is not None and idea.qual.supports_outlier is False:
        blocks.append("qualitative denies quant outlier")
    if idea.catalysts is not None and not idea.catalysts.tradeable:
        low, high = catalyst_window()
        blocks.append(f"no dated {low}-{high}d catalysts (investment idea only)")
    blocks.extend(quantification_gate(idea))
    blocks.extend(revision_veto_gate(idea))
    return blocks


def revision_veto_gate(idea: TradeIdea) -> list[str]:
    """Block a name whose own filings point against the revision ranking it.

    The book follows revision momentum, so this is the one place filings still
    bite. Framed as a risk control rather than a signal: filings are backward
    looking and cannot establish that analysts are wrong, but following a
    revision that a company's own reported numbers contradict is a bet nobody
    asked for. Set [filters] revision_veto = false to rank on momentum alone.
    """
    if not bool((toml_settings()["filters"]).get("revision_veto", True)):
        return []
    if idea.qual is None or idea.qual.supports_outlier is not True:
        return []
    from ptm.drift import consensus_drift, filings_veto

    drift = consensus_drift(idea.extra.get("expectations"))
    reason = filings_veto(drift, idea.qual)
    return [reason] if reason else []


def quantification_gate(idea: TradeIdea) -> list[str]:
    """A passing verdict must be able to size at least one of its reasons.

    Applied only to verdicts that came back true: this is a quality bar on a
    pass, not a second way to fail. Reasons are counted after `reconcile_sides`
    has re-filed any that argue for the other side, so a wrong-signed figure
    cannot satisfy the floor.

    Two names in one book reached it on three unquantified reasons each - OGN
    ("decreasing demand", "pricing pressure", "volume declines") and RSI
    ("record revenue", "share gains"). Both were rejected by two independent
    human reviews on exactly this basis: a level is not a change, and a claim
    nobody sized cannot be weighed against what the market already expects.
    """
    need = int((toml_settings()["filters"]).get("min_quantified_for") or 0)
    if not need or idea.qual is None or idea.qual.supports_outlier is not True:
        return []
    from ptm.ranking import reconcile_sides

    for_items, _, _ = reconcile_sides(idea.qual, idea.candidate.side)
    have = sum(1 for item in for_items if item.quantified)
    if have >= need:
        return []
    return [f"only {have} quantified reason(s) for the trade (need {need})"]


def size_fraction(idea: TradeIdea) -> float:
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
