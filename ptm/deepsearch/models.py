"""Pydantic models for the deep single-ticker qualitative dive."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """Where a claim came from: a web-search result, a fetched page or a filing."""

    title: str = ""
    url: str = ""
    date: str = ""  # publication date when the source states one, else ""


class SearchFinding(BaseModel):
    """One claim extracted from web research, with the source that carries it."""

    claim: str = ""
    source: SourceRef = Field(default_factory=SourceRef)
    category: str = ""  # business | industry | competition | catalyst | sentiment
    dated: str = ""  # when the underlying event happened, when known


class Driver(BaseModel):
    """A named qualitative driver the thesis rests on."""

    name: str = ""
    direction: str = ""  # tailwind | headwind
    evidence: str = ""
    source: SourceRef = Field(default_factory=SourceRef)
    confidence: str = "medium"  # high | medium | low
    # Written by the synthesis pass together with the stance: the analyst's own
    # scoring of this driver's debate, from the standpoint of the STOCK
    # (bull-won round positive, bear-won negative) on a -2..+2 scale. The
    # category is the pillar the driver belongs to; FIXED weights in
    # ptm/deepsearch/verdict.py roll the scores up into the evidence score S.
    score: float | None = None
    category: str = ""  # valuation | fundamentals | catalysts | competitive | risk
    score_why: str = ""


class BullPoint(BaseModel):
    point: str = ""
    evidence: str = ""
    source: SourceRef = Field(default_factory=SourceRef)
    strength: str = "medium"  # strong | medium | weak


class BearPoint(BaseModel):
    point: str = ""
    evidence: str = ""
    source: SourceRef = Field(default_factory=SourceRef)
    severity: str = "medium"  # severe | material | minor


class MacroImplication(BaseModel):
    """One transmission channel from the macro backdrop into the company."""

    channel: str = ""
    direction: str = ""  # helps | hurts | mixed
    why: str = ""


class MacroView(BaseModel):
    """The PTM dashboard state projected onto ONE ticker.

    Deterministic fields are read from curated macro/ISM files; `narrative`
    and `implications` come from an LLM pass that works out how the backdrop
    transmits into this company's fundamentals.
    """

    available: bool = False
    reason: str = ""
    sector: str = ""
    industry: str = ""
    bias: str = ""
    pmi: float | None = None
    nmi: float | None = None
    new_orders: float | None = None
    tens_minus_twos: float | None = None
    vix: float | None = None
    spx_in_bear: bool | None = None
    ism_report_month: str = ""
    sector_tilt: str = ""
    sector_score: float = 0.0
    sector_why: str = ""
    industry_flags: list[dict] = Field(default_factory=list)
    respondent_comments: list[dict] = Field(default_factory=list)
    snapshot_notes: list[str] = Field(default_factory=list)
    narrative: str = ""
    implications: list[MacroImplication] = Field(default_factory=list)
    llm_used: bool = False


class Catalyst(BaseModel):
    event: str = ""
    window: str = ""  # e.g. "Q3 print due early November", "FDA decision H1 2027"
    expected: str = ""  # what each outcome would do to the thesis
    source: SourceRef = Field(default_factory=SourceRef)


class DebateRound(BaseModel):
    """One exchange between the bull and the bear on the SAME driver."""

    driver: str = ""
    bull: str = ""
    bull_source: SourceRef = Field(default_factory=SourceRef)
    bear: str = ""
    bear_source: SourceRef = Field(default_factory=SourceRef)
    verdict: str = ""  # who won on THIS driver and why
    verdict_side: str = ""  # bull | bear | tie


class Thesis(BaseModel):
    """The final synthesis: the model's own view, not a restatement of the pack."""

    stance: str = "unclear"  # constructive | cautious | balanced | unclear
    thesis: str = ""
    drivers: list[Driver] = Field(default_factory=list)
    bull_case: list[BullPoint] = Field(default_factory=list)
    bear_case: list[BearPoint] = Field(default_factory=list)
    debate: list[DebateRound] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)
    confidence: str = "medium"  # high | medium | low
    confidence_why: str = ""


class DeepResearch(BaseModel):
    """Everything the web pass gathered and concluded about one ticker."""

    ticker: str
    as_of: str = ""
    queries_run: list[str] = Field(default_factory=list)
    findings: list[SearchFinding] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    fetched_pages: list[SourceRef] = Field(default_factory=list)
    search_used: bool = False
    error: str = ""


class DeepResult(BaseModel):
    """The full output of one deep dive."""

    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    as_of: str = ""
    research: DeepResearch | None = None
    thesis: Thesis | None = None
    macro: MacroView | None = None
    catalysts: list[Catalyst] = Field(default_factory=list)
    llm_used: bool = False
    models_used: list[str] = Field(default_factory=list)
    error: str = ""