from collections import Counter

from ptm.book import assemble_book
from ptm.models import Bias, Candidate, IdeaState, PRMResult, Side, TradeIdea


SECTORS = ["Industrials", "Financials", "Energy", "Materials", "Utilities", "Health Care"]


def _idea(
    ticker: str,
    side: Side,
    *,
    templated: bool = True,
    extra_gates: list[str] | None = None,
    beta: float = 0.2,
    sector: str | None = None,
) -> TradeIdea:
    # Distinct sectors by default: these tests are about splits, gates and beta,
    # not concentration, and an empty sector would collide under the per-sector cap.
    if sector is None:
        sector = SECTORS[abs(hash(ticker)) % len(SECTORS)]
    idea = TradeIdea(
        candidate=Candidate(
            ticker=ticker, side=side, name=ticker, sector=sector, market_cap=50e9
        ),
        state=IdeaState.TEMPLATED if templated else IdeaState.IDENTIFIED,
        prm=PRMResult(blocked=False, beta=beta, size_fraction=1.0, r_score=3.0),
    )
    if extra_gates:
        idea.extra["gates"] = extra_gates
    return idea


def test_assemble_book_splits_and_limits():
    ideas = [_idea(f"L{i}", Side.LONG, sector=SECTORS[i % len(SECTORS)]) for i in range(8)]
    ideas += [_idea(f"S{i}", Side.SHORT, sector=SECTORS[i % len(SECTORS)]) for i in range(8)]
    book = assemble_book(ideas, Bias.NET_LONG)
    assert len(book.ideas) == 12
    assert sum(1 for i in book.ideas if i.candidate.side == Side.LONG) == 6
    assert sum(1 for i in book.ideas if i.candidate.side == Side.SHORT) == 6
    assert all(i.state == IdeaState.SIZED for i in book.ideas)


def test_assemble_book_excludes_gates_not_timing():
    gated = _idea("G1", Side.LONG, extra_gates=["qualitative denies quant outlier"])
    identified = _idea("I1", Side.LONG, templated=False)
    ok = _idea("L1", Side.LONG)
    book = assemble_book([gated, identified, ok], Bias.NEUTRAL)
    tickers = {i.candidate.ticker for i in book.ideas}
    assert "G1" not in tickers
    assert "I1" not in tickers
    assert "L1" in tickers


def test_empty_ready_set_is_a_breach():
    book = assemble_book([], Bias.NET_LONG)
    assert book.ideas == []
    assert any("only 0 names" in b for b in book.limit_breaches)


def test_size_stays_full_and_beta_breach():
    ideas = [_idea("L1", Side.LONG, beta=0.1), _idea("S1", Side.SHORT, beta=2.0)]
    book = assemble_book(ideas, Bias.NET_LONG)
    long = next(i for i in book.ideas if i.candidate.side == Side.LONG)
    assert long.prm is not None and long.prm.size_fraction == 1.0
    assert any("beta" in b.lower() for b in book.limit_breaches)


def _ready_idea(ticker: str, sector: str, side: Side, market_cap: float = 50e9) -> TradeIdea:
    return TradeIdea(
        candidate=Candidate(
            ticker=ticker, name=ticker, sector=sector, side=side, market_cap=market_cap
        ),
        state=IdeaState.TEMPLATED,
        prm=PRMResult(beta=1.0),
    )


def test_book_spreads_across_sectors():
    """Six shorts drawn from one sector is one bet, not six."""
    pool = [_ready_idea(f"F{i}", "Financials", Side.SHORT) for i in range(6)]
    pool += [_ready_idea("IND1", "Industrials", Side.SHORT), _ready_idea("EN1", "Energy", Side.SHORT)]
    book = assemble_book(pool, Bias.NEUTRAL)
    sectors = [i.candidate.sector for i in book.ideas]
    assert sectors.count("Financials") == 2, "the per-sector cap must bind"
    assert set(sectors) == {"Financials", "Industrials", "Energy"}
    assert len(book.ideas) == 4


def test_rank_order_is_preserved_within_the_cap():
    """The cap picks the BEST names per sector, not arbitrary ones."""
    pool = [
        _ready_idea("BEST", "Financials", Side.LONG),
        _ready_idea("SECOND", "Financials", Side.LONG),
        _ready_idea("THIRD", "Financials", Side.LONG),
        _ready_idea("OTHER", "Energy", Side.LONG),
    ]
    book = assemble_book(pool, Bias.NEUTRAL)
    picked = [i.candidate.ticker for i in book.ideas]
    assert picked[:2] == ["BEST", "SECOND"]
    assert "THIRD" not in picked, "the cap must not be topped up from a full sector"


def test_cap_reports_rather_than_silently_relaxing():
    """A concentrated book would hide correlated risk, so the side comes back
    short and says so."""
    pool = [_ready_idea(f"F{i}", "Financials", Side.LONG) for i in range(6)]
    book = assemble_book(pool, Bias.NEUTRAL)
    assert len(book.ideas) == 2, "the 2-per-sector cap binds"
    assert any("per-sector cap" in b for b in book.limit_breaches)
    assert any("names" in b for b in book.limit_breaches), "under-size is still reported"


def _beta_idea(ticker: str, sector: str, side: Side, beta: float) -> TradeIdea:
    return TradeIdea(
        candidate=Candidate(
            ticker=ticker, name=ticker, sector=sector, side=side, market_cap=50e9
        ),
        state=IdeaState.TEMPLATED,
        prm=PRMResult(beta=beta),
    )


def test_beta_rebalance_brings_a_breaching_book_inside_the_limit():
    """A P/E screen is beta-long by construction: growth longs, value shorts.
    Equal-weighting a dollar-neutral book still breaches, so selection swaps."""
    # Rank order puts the high-beta names first, so the naive pick breaches;
    # the calm names sit on the bench, which is what a real run looks like
    # (75 ready longs competing for 6 slots).
    hot = ["Industrials", "Industrials", "Energy", "Energy", "Materials", "Materials"]
    calm = ["Utilities", "Utilities", "Real Estate", "Real Estate", "Consumer Staples", "Consumer Staples"]
    pool = [_beta_idea(f"HOT{i}", s, Side.LONG, 2.5) for i, s in enumerate(hot)]
    pool += [_beta_idea(f"CALM{i}", s, Side.LONG, 0.15) for i, s in enumerate(calm)]
    pool += [
        _beta_idea("DEF1", "Health Care", Side.SHORT, 0.15),
        _beta_idea("DEF2", "Communication Services", Side.SHORT, 0.15),
    ]
    naive = (6 * 2.5 - 2 * 0.15) / 8
    assert naive > 0.30, "fixture must actually breach before rebalancing"

    book = assemble_book(pool, Bias.NEUTRAL)
    assert abs(book.portfolio_beta) <= 0.30, f"beta {book.portfolio_beta} still breaches"
    assert any("beta rebalance" in b for b in book.limit_breaches), "swaps must be reported"
    picked = {i.candidate.ticker for i in book.ideas if i.candidate.side == Side.LONG}
    assert any(t.startswith("CALM") for t in picked), "low-beta bench names should be pulled in"


def test_beta_rebalance_respects_the_sector_cap():
    pool = [_beta_idea(f"HOT{i}", "Industrials", Side.LONG, 2.5) for i in range(2)]
    pool += [_beta_idea(f"CALM{i}", "Financials", Side.LONG, 0.1) for i in range(4)]
    pool += [_beta_idea("S1", "Energy", Side.SHORT, 0.1), _beta_idea("S2", "Utilities", Side.SHORT, 0.1)]
    book = assemble_book(pool, Bias.NEUTRAL)
    sectors = Counter(i.candidate.sector for i in book.ideas)
    assert all(v <= 2 for v in sectors.values()), f"cap violated by rebalance: {dict(sectors)}"


def test_rank_leads_when_beta_already_complies():
    """No swaps when the book is already inside the limit."""
    pool = [
        _beta_idea("BEST", "Industrials", Side.LONG, 0.9),
        _beta_idea("ALSO", "Energy", Side.LONG, 0.9),
        _beta_idea("S1", "Materials", Side.SHORT, 0.9),
        _beta_idea("S2", "Utilities", Side.SHORT, 0.9),
    ]
    book = assemble_book(pool, Bias.NEUTRAL)
    assert abs(book.portfolio_beta) <= 0.30
    assert not any("beta rebalance" in b for b in book.limit_breaches)
    assert {i.candidate.ticker for i in book.ideas} == {"BEST", "ALSO", "S1", "S2"}


def test_beta_selection_can_be_switched_off(monkeypatch):
    import ptm.book as bookmod
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "filters": {**base["filters"], "beta_aware_selection": False}}
    monkeypatch.setattr(bookmod, "toml_settings", lambda: patched)
    pool = [
        _beta_idea("HOT1", "Industrials", Side.LONG, 2.5),
        _beta_idea("CALM1", "Materials", Side.LONG, 0.2),
        _beta_idea("DEF1", "Consumer Staples", Side.SHORT, 0.1),
    ]
    book = assemble_book(pool, Bias.NEUTRAL)
    assert not any("beta rebalance" in b for b in book.limit_breaches)


def test_short_book_limits_names_below_the_mcap_floor():
    """Small-cap shorts carry borrow, squeeze and liquidity risk large caps do
    not. Three of six sub-$20bn shorts is a different strategy than intended."""
    pool = [
        _ready_idea("BIG1", "Financials", Side.SHORT, market_cap=60e9),
        _ready_idea("SMALL1", "Health Care", Side.SHORT, market_cap=3e9),
        _ready_idea("SMALL2", "Real Estate", Side.SHORT, market_cap=2e9),
        _ready_idea("SMALL3", "Utilities", Side.SHORT, market_cap=1e9),
        _ready_idea("BIG2", "Energy", Side.SHORT, market_cap=40e9),
    ]
    book = assemble_book(pool, Bias.NEUTRAL)
    shorts = [i for i in book.ideas if i.candidate.side == Side.SHORT]
    small = [i for i in shorts if (i.candidate.market_cap or 0) < 20e9]
    assert len(small) == 1, f"expected 1 sub-floor short, got {[i.candidate.ticker for i in small]}"
    # Rank order still leads within the constraint.
    assert small[0].candidate.ticker == "SMALL1"
    assert {"BIG1", "BIG2"} <= {i.candidate.ticker for i in shorts}
    assert any("below $20bn" in b for b in book.limit_breaches)


def test_missing_market_cap_counts_as_below_the_floor():
    """We cannot confirm the name is large enough, and an unborrowable micro-cap
    short is exactly the risk this guards against."""
    pool = [
        _ready_idea("BIG", "Financials", Side.SHORT, market_cap=60e9),
        TradeIdea(
            candidate=Candidate(ticker="UNKNOWN", name="U", sector="Energy", side=Side.SHORT),
            state=IdeaState.TEMPLATED,
            prm=PRMResult(beta=1.0),
        ),
        _ready_idea("SMALL", "Utilities", Side.SHORT, market_cap=2e9),
    ]
    book = assemble_book(pool, Bias.NEUTRAL)
    picked = {i.candidate.ticker for i in book.ideas}
    assert "BIG" in picked
    assert not ({"UNKNOWN", "SMALL"} <= picked), "only one may be under the floor"


def test_long_side_is_not_subject_to_the_short_size_cap():
    pool = [_ready_idea(f"L{i}", s, Side.LONG, market_cap=4e9)
            for i, s in enumerate(["Industrials", "Energy", "Materials", "Utilities"])]
    book = assemble_book(pool, Bias.NEUTRAL)
    assert len(book.ideas) == 4, "the short-side floor must not filter longs"


def _conv_idea(ticker, sector, side, ism, eg1, for_n, against_n, flags=None):
    from ptm.models import QualResult

    return TradeIdea(
        candidate=Candidate(
            ticker=ticker, name=ticker, sector=sector, side=side,
            market_cap=50e9, mcap_ok=True, ism_score=ism, eg1=eg1,
        ),
        state=IdeaState.TEMPLATED,
        prm=PRMResult(beta=0.5),
        qual=QualResult(
            supports_outlier=True,
            evidence_for=[f"for{i}" for i in range(for_n)],
            evidence_against=[f"against{i}" for i in range(against_n)],
            red_flags=list(flags or []),
        ),
    )


def test_conviction_outranks_eg1_but_not_the_screen_proper():
    """Conviction beats earnings growth, but size band and ISM tilt still lead."""
    from ptm.ranking import ordered_ideas

    # Equal on mcap_ok and ISM -> conviction decides, eg1 no longer does.
    weak = _conv_idea("WEAK", "Industrials", Side.LONG, ism=1.0, eg1=0.90, for_n=1, against_n=3)
    strong = _conv_idea("STRONG", "Industrials", Side.LONG, ism=1.0, eg1=0.10, for_n=4, against_n=0)
    assert [i.candidate.ticker for i in ordered_ideas([weak, strong])] == ["STRONG", "WEAK"]

    # A better ISM score outranks higher conviction: the screen is not overridden.
    better_screen = _conv_idea("SCREEN", "Energy", Side.LONG, ism=2.0, eg1=0.10, for_n=0, against_n=2)
    order = [i.candidate.ticker for i in ordered_ideas([strong, better_screen])]
    assert order == ["SCREEN", "STRONG"]


def test_process_failures_dock_conviction_but_business_risks_do_not():
    """A red flag about tariffs is the analysis working; one about the model
    contradicting itself is the analysis failing."""
    from ptm.ranking import conviction

    base = _conv_idea("A", "Industrials", Side.LONG, 1.0, 0.2, for_n=3, against_n=1)
    assert conviction(base) == 2

    business = _conv_idea("B", "Industrials", Side.LONG, 1.0, 0.2, for_n=3, against_n=1,
                          flags=["Tariff exposure in China", "Rising input costs"])
    assert conviction(business) == 2, "business risks must not dock conviction"

    downgraded = _conv_idea("C", "Industrials", Side.LONG, 1.0, 0.2, for_n=3, against_n=1,
                            flags=["verdict_model_downgraded_to_meta/llama-3.1-8b-instruct"])
    assert conviction(downgraded) == 1, "a downgraded verdict is weaker evidence"


def test_shorts_still_prefer_more_negative_growth_within_a_conviction_level():
    from ptm.ranking import ordered_ideas

    shrinking = _conv_idea("SHRINK", "Industrials", Side.SHORT, ism=1.0, eg1=-0.40, for_n=2, against_n=0)
    flat = _conv_idea("FLAT", "Industrials", Side.SHORT, ism=1.0, eg1=0.10, for_n=2, against_n=0)
    # Equal conviction -> the short key's eg1 direction still decides.
    assert [i.candidate.ticker for i in ordered_ideas([flat, shrinking])] == ["SHRINK", "FLAT"]


def test_qual_rank_can_be_switched_off(monkeypatch):
    import ptm.ranking as ranking
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "filters": {**base["filters"], "qual_rank": False}}
    monkeypatch.setattr(ranking, "toml_settings", lambda: patched)
    weak = _conv_idea("WEAK", "Industrials", Side.LONG, ism=1.0, eg1=0.90, for_n=1, against_n=3)
    strong = _conv_idea("STRONG", "Industrials", Side.LONG, ism=1.0, eg1=0.10, for_n=4, against_n=0)
    assert [i.candidate.ticker for i in ranking.ordered_ideas([weak, strong])] == ["WEAK", "STRONG"]


def _ev(claim, pct=None, on="none", quantified=False):
    from ptm.models import EvidenceItem

    return EvidenceItem(claim=claim, impact_pct=pct, impact_on=on, quantified=quantified)


def test_quantified_evidence_outweighs_vague_evidence():
    """Counting made 'backlog up 22%' and 'management sounds confident' equal, so
    four vague reasons beat two quantified ones."""
    from ptm.models import QualResult
    from ptm.ranking import conviction

    vague = TradeIdea(
        candidate=Candidate(ticker="VAGUE", side=Side.LONG, name="V"),
        qual=QualResult(supports_outlier=True, evidence_for=[
            _ev("well positioned"), _ev("strong culture"), _ev("good management"), _ev("large market")]),
    )
    hard = TradeIdea(
        candidate=Candidate(ticker="HARD", side=Side.LONG, name="H"),
        qual=QualResult(supports_outlier=True, evidence_for=[
            _ev("EPS guidance raised 25%", pct=25.0, on="earnings", quantified=True),
            _ev("revenue up 18%", pct=18.0, on="revenue", quantified=True)]),
    )
    assert conviction(vague) == 4.0, "four vague reasons still score their base weight"
    assert conviction(hard) > conviction(vague), f"{conviction(hard)} !> {conviction(vague)}"


def test_impact_scope_orders_earnings_above_revenue_above_margin():
    from ptm.ranking import evidence_weight

    same = 20.0
    e = evidence_weight(_ev("x", pct=same, on="earnings", quantified=True))
    r = evidence_weight(_ev("x", pct=same, on="revenue", quantified=True))
    m = evidence_weight(_ev("x", pct=same, on="margin", quantified=True))
    n = evidence_weight(_ev("x", pct=same, on="none", quantified=True))
    assert e > r > m > n > 1.0


def test_a_huge_number_cannot_dominate_the_score():
    """A 300% figure off a near-zero base must score no more than a solid 30% one,
    so an artefact of a tiny denominator cannot buy its way up the book."""
    from ptm.ranking import BASE_WEIGHT, MAX_BONUS, evidence_weight

    absurd = evidence_weight(_ev("EPS up 300%", pct=300.0, on="earnings", quantified=True))
    capped = evidence_weight(_ev("EPS up 30%", pct=30.0, on="earnings", quantified=True))
    assert absurd == capped == BASE_WEIGHT + MAX_BONUS
    # The whole scale is bounded: no single claim can run away with the score.
    assert absurd <= 4 * evidence_weight(_ev("an unquantified reason"))


def test_unquantified_claims_keep_the_old_count_behaviour():
    """Nothing is lost when a model declines to quantify."""
    from ptm.models import QualResult
    from ptm.ranking import conviction

    idea = TradeIdea(
        candidate=Candidate(ticker="X", side=Side.LONG, name="X"),
        qual=QualResult(supports_outlier=True,
                        evidence_for=[_ev("a"), _ev("b"), _ev("c")],
                        evidence_against=[_ev("d")]),
    )
    assert conviction(idea) == 2.0


def test_invented_magnitudes_are_stripped_at_parse_time():
    """A precise number the model made up is worse than no number at all."""
    from ptm.llm import _evidence_items

    items = _evidence_items([
        {"claim": "EPS up 40%", "impact_pct": 40.0, "impact_on": "earnings", "quantified": True},
        {"claim": "feels strong", "impact_pct": 15.0, "impact_on": "earnings", "quantified": False},
        {"claim": "no number given", "impact_pct": None, "impact_on": "earnings", "quantified": True},
        "a bare string from a simpler model",
    ])
    assert [i.quantified for i in items] == [True, False, False, False]
    # quantified=False must also drop the magnitude, not just the flag.
    assert items[1].impact_pct is None and items[1].impact_on == "none"
    assert items[2].impact_pct is None
    assert items[3].claim.startswith("a bare string")
