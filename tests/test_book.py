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
        candidate=Candidate(ticker=ticker, side=side, name=ticker, sector=sector),
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


def _ready_idea(ticker: str, sector: str, side: Side) -> TradeIdea:
    return TradeIdea(
        candidate=Candidate(ticker=ticker, name=ticker, sector=sector, side=side),
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
        candidate=Candidate(ticker=ticker, name=ticker, sector=sector, side=side),
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
