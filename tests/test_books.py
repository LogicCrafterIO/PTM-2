from ptm.book import assemble_book
from ptm.books import window_of
from ptm.models import Bias, Candidate, EarningsEstimate, Side, TradeIdea


def test_window_uses_stored_run_date_distance():
    idea = TradeIdea(
        candidate=Candidate(ticker="BOUNDARY", side=Side.LONG),
        earnings=EarningsEstimate(
            ticker="BOUNDARY",
            date="2099-01-01",
            days_to_earnings=61,
            estimated=True,
        ),
    )

    assert window_of(idea) == "61-90d"


def test_window_without_stored_distance_is_not_recomputed():
    idea = TradeIdea(
        candidate=Candidate(ticker="UNKNOWN", side=Side.LONG),
        earnings=EarningsEstimate(ticker="UNKNOWN", date="2099-01-01"),
    )

    assert window_of(idea) is None


def test_nonpersistent_book_does_not_replace_aggregate(monkeypatch):
    writes: list[str] = []
    monkeypatch.setattr("ptm.book.write_json", lambda path, payload: writes.append(path.name))

    assemble_book([], Bias.NEUTRAL, persist=False)
    assert writes == []

    assemble_book([], Bias.NEUTRAL)
    assert writes == ["book.json"]
