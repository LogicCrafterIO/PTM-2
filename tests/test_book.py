from ptm.book import assemble_book
from ptm.models import Bias, Candidate, IdeaState, PRMResult, Side, TradeIdea


def _idea(ticker: str, side: Side, *, templated: bool = True, extra_gates: list[str] | None = None, beta: float = 0.2) -> TradeIdea:
    idea = TradeIdea(
        candidate=Candidate(ticker=ticker, side=side, name=ticker),
        state=IdeaState.TEMPLATED if templated else IdeaState.IDENTIFIED,
        prm=PRMResult(blocked=False, beta=beta, size_fraction=1.0, r_score=3.0),
    )
    if extra_gates:
        idea.extra["gates"] = extra_gates
    return idea


def test_assemble_book_splits_and_limits():
    ideas = [_idea(f"L{i}", Side.LONG) for i in range(8)] + [_idea(f"S{i}", Side.SHORT) for i in range(8)]
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
