from ptm.book import assemble_book
from ptm.models import Bias, Candidate, IdeaState, PRMResult, Side, TimingLight, TimingResult, TradeIdea


def _idea(ticker: str, side: Side, *, templated: bool = True, blocked: bool = False, amber: bool = False, beta: float = 0.2) -> TradeIdea:
    return TradeIdea(
        candidate=Candidate(ticker=ticker, side=side, name=ticker),
        state=IdeaState.TEMPLATED if templated else IdeaState.IDENTIFIED,
        timing=TimingResult(light=TimingLight.AMBER if amber else TimingLight.GREEN),
        prm=PRMResult(blocked=blocked, beta=beta, size_fraction=1.0, r_score=3.0),
    )


def test_assemble_book_splits_and_limits():
    ideas = [_idea(f"L{i}", Side.LONG) for i in range(8)] + [_idea(f"S{i}", Side.SHORT) for i in range(8)]
    book = assemble_book(ideas, Bias.NET_LONG)
    assert len(book.ideas) == 12
    assert sum(1 for i in book.ideas if i.candidate.side == Side.LONG) == 6
    assert sum(1 for i in book.ideas if i.candidate.side == Side.SHORT) == 6
    assert all(i.state == IdeaState.SIZED for i in book.ideas)


def test_assemble_book_excludes_gates_and_prm_blocked():
    gated = _idea("G1", Side.LONG)
    gated.extra["gates"] = ["timing red: do not enter"]
    blocked = _idea("B1", Side.LONG, blocked=True)
    identified = _idea("I1", Side.LONG, templated=False)
    zero = _idea("Z1", Side.LONG)
    assert zero.prm is not None
    zero.prm.size_fraction = 0.0
    book = assemble_book([gated, blocked, identified, zero], Bias.NEUTRAL)
    tickers = {i.candidate.ticker for i in book.ideas}
    assert "G1" not in tickers
    assert "B1" not in tickers
    assert "I1" not in tickers
    assert "Z1" not in tickers
    assert any("only" in b and "names" in b for b in book.limit_breaches)


def test_empty_ready_set_is_a_breach():
    book = assemble_book([], Bias.NET_LONG)
    assert book.ideas == []
    assert any("only 0 names" in b for b in book.limit_breaches)


def test_amber_halves_size_and_beta_breach():
    ideas = [_idea("L1", Side.LONG, amber=True, beta=2.0), _idea("S1", Side.SHORT, beta=2.0)]
    book = assemble_book(ideas, Bias.NET_LONG)
    long = next(i for i in book.ideas if i.candidate.side == Side.LONG)
    assert long.prm is not None and long.prm.size_fraction == 0.5
    assert any("beta" in b.lower() for b in book.limit_breaches)
