from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
    permits_yoy: float | None = None
    permits_3m3m: float | None = None
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
    # Multiple premium per unit of growth premium; see formulas.relative_peg.
    relative_peg: float | None = None
    eg_case: str = ""
    mcap_ok: bool = True
    mcap_warning: str = ""
    ism_score: float = 0.0
    ism_tilt: str = "neutral"
    ism_why: str = ""
    evidence: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """One reason for or against a trade, with its size where the filing gives one.

    Counting reasons treats "backlog up 22%" and "management sounds confident"
    as equal. `impact_pct` and `impact_on` carry the magnitude so conviction can
    weigh them; `quantified` records whether that number actually appeared in the
    research pack, so an inferred figure can never masquerade as a reported one.
    """

    claim: str = ""
    metric: str = ""
    impact_pct: float | None = None
    # What the number moves: earnings, revenue, margin, or nothing measurable.
    impact_on: str = "none"
    quantified: bool = False

    @classmethod
    def coerce(cls, value: object) -> EvidenceItem:
        """Accept a bare string, as older runs and simpler models produce."""
        if isinstance(value, EvidenceItem):
            return value
        if isinstance(value, dict):
            return cls.model_validate(value)
        return cls(claim=str(value or "").strip())


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
    evidence_for: list[EvidenceItem] = Field(default_factory=list)
    evidence_against: list[EvidenceItem] = Field(default_factory=list)
    denial_reason: str = ""

    @field_validator("evidence_for", "evidence_against", mode="before")
    @classmethod
    def _accept_strings(cls, value: object) -> object:
        """Runs written before evidence was structured stay loadable."""
        if isinstance(value, list):
            return [EvidenceItem.coerce(item) for item in value]
        return value
    # What the market already assumes going into the print, and how the evidence
    # differs from it. Without these a valuation argument becomes an earnings
    # trade with nothing said about what is priced - the single complaint three
    # independent reviews of one book all made.
    market_expectation: str = ""
    deviation: str = ""
    # already_priced | partly_priced | not_priced | unknown
    priced_in: str = "unknown"
    # THE number the whole qualitative pass exists to produce: how far the sized
    # evidence points above (or below) the consensus FY1 EPS the market is
    # holding. Positive means the evidence points above consensus. This is what
    # makes one idea rankable against another - `deviation` says a gap exists,
    # this says how big it is. None when the evidence cannot support a figure;
    # a guessed number here would be worse than no number.
    expected_surprise_pct: float | None = None
    # Which of the listed reasons drive that figure, so it can be checked.
    surprise_basis: str = ""
    # high | medium | low | none
    gap_confidence: str = "none"
    # WHAT the gap rests on. guidance | forward_indicator | run_rate | none
    gap_basis_type: str = "none"
    # The model's ONE job on the expectation gap now: which way do the filings
    # point? A classification, not a calculation. Asking for a percentage
    # produced round-number clustering and constant confidence, because backing
    # out a consensus-implied growth rate is arithmetic a mid-sized model cannot
    # do. The magnitude comes from measured analyst revisions instead - see
    # ptm/drift.py. improving | deteriorating | mixed | silent
    filing_direction: str = "silent"
    # Which specific figures drove that call, so it can be checked.
    direction_basis: str = ""
    # Is the run still going, or lapping? The screen returns quantitative
    # outliers, so by construction a re-rating has usually STARTED - which makes
    # "how much is left" the live question rather than "has it begun". A model
    # cannot measure that, but it can read a filing for the difference between
    # guidance raised again and guidance merely reaffirmed, backlog still
    # building and backlog flat, a tailwind arriving and one lapping.
    # building | intact | fading | exhausted | unclear
    momentum_durability: str = "unclear"
    durability_basis: str = ""
    # Global themes this name is exposed to, from ptm/themes.py.
    themes: list[str] = Field(default_factory=list)


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
    """Position risk. Beta is the only measured field left.

    stop_pct, target_pct, r_score and atrp were removed with the move to
    options: a stop distance on the underlying does not manage a defined-risk
    position, and none of the four gated or ranked anything. See ptm/risk.py.
    """

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
    # How many names the model actually wrote a comment for. Large groups used
    # to silently come back with ~8 of 137 covered.
    covered: int = 0
    ranked_by_model: int = 0
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
