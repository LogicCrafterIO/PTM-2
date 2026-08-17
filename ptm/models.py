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


class TimingLight(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    UNKNOWN = "unknown"


class IdeaState(str, Enum):
    IDENTIFIED = "identified"
    QUAL_PASS = "qual_pass"
    QUAL_FAIL = "qual_fail"
    CATALYST_PASS = "catalyst_pass"
    INVESTMENT_ONLY = "investment_only"
    TIMED = "timed"
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
    denial_reason: str = ""


class CatalystResult(BaseModel):
    earnings_date: str | None = None
    earnings_in_window: bool = False
    non_earnings: list[str] = Field(default_factory=list)
    tradeable: bool = False
    reason: str = ""


class TimingResult(BaseModel):
    light: TimingLight = TimingLight.UNKNOWN
    sma20: float | None = None
    sma60: float | None = None
    ema20: float | None = None
    ema60: float | None = None
    macd: float | None = None
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


class TradeIdea(BaseModel):
    candidate: Candidate
    state: IdeaState = IdeaState.IDENTIFIED
    qual: QualResult | None = None
    catalysts: CatalystResult | None = None
    timing: TimingResult | None = None
    prm: PRMResult | None = None
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
