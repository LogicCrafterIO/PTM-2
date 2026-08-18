from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Bias(str, Enum):
    NET_LONG = "NET_LONG"
    NEUTRAL = "NEUTRAL"
    NET_SHORT = "NET_SHORT"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class IdeaState(str, Enum):
    IDENTIFIED = "identified"
    QUAL_PASS = "qual_pass"
    QUAL_FAIL = "qual_fail"
    CATALYST_PASS = "catalyst_pass"
    INVESTMENT_ONLY = "investment_only"
    TEMPLATED = "templated"
    SIZED = "sized"


class UniverseName(BaseModel):
    ticker: str
    name: str
    sector: str = ""
    industry: str = ""
    indices: list[str] = Field(default_factory=list)


class MacroSnapshot(BaseModel):
    as_of: str
    spx_last: float | None = None
    bear_level: float | None = None
    in_bear: bool | None = None
    tens_minus_twos: float | None = None
    curve_inverted: bool | None = None
    curve_second_leg: str = ""
    real_10y: float | None = None
    vix: float | None = None
    ism_pmi: float | None = None
    ism_nmi: float | None = None
    umcsi: float | None = None
    m2_yoy: float | None = None
    signals: dict[str, float] = Field(default_factory=dict)
    score: float = 0.0
    bias: Bias = Bias.NEUTRAL
    notes: list[str] = Field(default_factory=list)
    llm_narrative: str = ""
    ism_new_orders: float | None = None
    sector_tilts: list[dict] = Field(default_factory=list)


class Candidate(BaseModel):
    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    side: Side
    price: float | None = None
    market_cap: float | None = None
    eps0: float | None = None
    eps1: float | None = None
    eps2: float | None = None
    eg1: float | None = None
    eg2: float | None = None
    pe1: float | None = None
    pe2: float | None = None
    peg1: float | None = None
    peg2: float | None = None
    sector_pe1: float | None = None
    sector_eg1: float | None = None
    eg_case: str = ""
    mcap_ok: bool = True
    mcap_warning: str = ""
    ism_score: float = 0.0
    ism_tilt: str = "neutral"
    ism_why: str = ""
    evidence: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class QualResult(BaseModel):
    supports_outlier: bool | None = None
    red_flags: list[str] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)
    operating_plan: str = ""
    summary: str = ""
    why: str = ""
    evidence_quotes: list[str] = Field(default_factory=list)
    # The verdict pass enumerates these before committing to supports_outlier,
    # so a boolean that contradicts its own evidence is visible rather than
    # silently wrong. See docs/FEATURE-LIMITATIONS.md.
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    denial_reason: str = ""


class CatalystResult(BaseModel):
    earnings_date: str | None = None
    earnings_in_window: bool = False
    non_earnings: list[str] = Field(default_factory=list)
    tradeable: bool = False
    reason: str = ""


class TimingResult(BaseModel):
    """Kept only to carry the note that timing is deliberately not modelled.

    The SMA/EMA/MACD fields this used to hold were removed: no technical
    analysis takes part in screening.
    """

    comment: str = ""


class PRMResult(BaseModel):
    stop_pct: float | None = None
    target_pct: float | None = None
    r_score: float | None = None
    atrp: float | None = None
    beta: float | None = None
    size_fraction: float = 1.0
    blocked: bool = False
    block_reason: str = ""


class EarningsEstimate(BaseModel):
    """When a name next reports, and how we know.

    `estimated` is True when no future date was published and the projection
    came from the company's own filing cadence. `basis` states that in full so
    the reader never sees a bare date they might mistake for a confirmed one.
    """

    ticker: str = ""
    date: str | None = None
    estimated: bool = False
    last_report: str | None = None
    cadence_days: int | None = None
    days_to_earnings: int | None = None
    basis: str = ""


class GroupNameView(BaseModel):
    ticker: str
    side: str = ""
    eg_case: str = ""
    qual_verdict: str = ""
    comment: str = ""


class GroupReview(BaseModel):
    """Second-pass LLM read across every idea sharing a sector or an earnings
    window, comparing their fundamental cases against each other.

    Contains no price or technical input by design — see
    docs/FEATURE-LIMITATIONS.md.
    """

    group_kind: str = "sector"
    group_label: str = ""
    as_of: str = ""
    tickers: list[str] = Field(default_factory=list)
    llm_used: bool = False
    summary: str = ""
    narrative: str = ""
    views: list[GroupNameView] = Field(default_factory=list)
    ranked_tickers: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    error: str = ""


class TradeIdea(BaseModel):
    candidate: Candidate
    state: IdeaState = IdeaState.IDENTIFIED
    qual: QualResult | None = None
    catalysts: CatalystResult | None = None
    timing: TimingResult | None = None
    prm: PRMResult | None = None
    earnings: EarningsEstimate | None = None
    template_markdown: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class BookProposal(BaseModel):
    as_of: str
    bias: Bias
    ideas: list[TradeIdea]
    gross_exposure: float | None = None
    net_exposure: float | None = None
    portfolio_beta: float | None = None
    limit_breaches: list[str] = Field(default_factory=list)
    narrative: str = ""
