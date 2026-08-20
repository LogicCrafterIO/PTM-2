from datetime import date

import pytest

from datetime import timedelta
from ptm.models import CatalystResult, Candidate, Side, TradeIdea
from ptm.organize import (
    BEYOND,
    bucket_for_days,
    bucket_names,
    find_idea_files,
    find_idea_markdown,
    group_by_bucket,
    group_by_sector,
    idea_paths,
    placements,
    sector_slug,
    write_index,
)

REF = date(2026, 8, 18)


def test_three_calendar_day_buckets():
    assert bucket_names() == ["00-30d", "31-60d", "61-90d"]


@pytest.mark.parametrize(
    "days,expected",
    [
        (0, "00-30d"),
        (30, "00-30d"),
        (31, "31-60d"),
        (60, "31-60d"),
        (61, "61-90d"),
        (90, "61-90d"),
        (91, BEYOND),
    ],
)
def test_bucket_edges_are_inclusive(days, expected):
    assert bucket_for_days(days) == expected


def test_buckets_and_catalyst_gate_share_units():
    """The PTM window is 20-60 trading days = 30-90 calendar days, and the
    buckets use the same units, so 31-60d and 61-90d names can satisfy the gate."""
    from ptm.risk import catalyst_window

    low, high = catalyst_window()
    assert (low, high) == (30, 90)
    assert bucket_for_days(low) in {"00-30d", "31-60d"}
    assert bucket_for_days(high) == "61-90d"
    # A name just past the window falls out of the three primary buckets.
    assert bucket_for_days(high + 1) == BEYOND


def test_removed_buckets_are_gone():
    """A past or missing date is projected forward, not dumped in a junk folder."""
    import ptm.organize as organize

    assert not hasattr(organize, "NO_DATE")
    assert not hasattr(organize, "PAST")
    names = set(bucket_names()) | {BEYOND}
    assert "no-earnings-date" not in names
    assert "already-reported" not in names


@pytest.mark.parametrize(
    "sector,slug",
    [
        ("Information Technology", "Information-Technology"),
        ("Health Care", "Health-Care"),
        ("", "Unclassified-Sector"),
        (None, "Unclassified-Sector"),
    ],
)
def test_sector_slug(sector, slug):
    assert sector_slug(sector) == slug


def _idea(ticker: str, sector: str, side: Side, earnings: str | None) -> TradeIdea:
    return TradeIdea(
        candidate=Candidate(ticker=ticker, name=ticker, sector=sector, side=side),
        catalysts=CatalystResult(earnings_date=earnings),
    )


def test_published_future_date_buckets_by_calendar_days(isolate_roots):
    thirty = REF + timedelta(days=30)
    idea = _idea("ACLS", "Information Technology", Side.LONG, thirty.isoformat())
    md, js = idea_paths(idea, day="2026-08-18", ref=REF)
    assert md.parent.name == "00-30d"
    assert md.parent.parent.name == "Information-Technology"
    assert md.name == "long_ACLS.md"
    assert idea.earnings.estimated is False
    assert idea.earnings.days_to_earnings == 30


def test_a_name_inside_the_catalyst_window_is_tradeable(isolate_roots):
    """The gate and the buckets must agree: a 31-60d name can pass."""
    from ptm.risk import earnings_in_window

    forty = REF + timedelta(days=40)
    idea = _idea("MID", "Industrials", Side.LONG, forty.isoformat())
    row = placements([idea], ref=REF)[0]
    assert row["bucket"] == "31-60d"
    in_window, _ = earnings_in_window(forty.isoformat(), low_days=30, high_days=90)
    assert in_window is True


def _no_network(monkeypatch, dates):
    """EDGAR filing history, stubbed. resolve() imports it lazily by module."""
    import ptm.ingest.edgar as edgar

    monkeypatch.setattr(edgar, "report_dates", lambda ticker, limit=8: list(dates))


def test_past_earnings_date_is_projected_forward(isolate_roots, monkeypatch):
    """Reported already, nothing scheduled: estimate a quarter on from the last one."""
    _no_network(monkeypatch, ["2026-05-05", "2026-02-04", "2025-11-05", "2025-08-06"])
    idea = _idea("ABT", "Health Care", Side.SHORT, "2026-05-05")
    rows = placements([idea], ref=REF)
    row = rows[0]
    assert row["earnings_estimated"] is True
    assert row["earnings_date"] > REF.isoformat()
    assert row["bucket"] in set(bucket_names())
    assert "no future earnings date published" in row["earnings_basis"]
    assert "last reported 2026-05-05" in row["earnings_basis"]
    assert row["bucket"] in row["earnings_note"]


def test_missing_date_with_no_filings_still_gets_a_bucket(isolate_roots, monkeypatch):
    _no_network(monkeypatch, [])
    idea = _idea("XYZ", "", Side.LONG, None)
    rows = placements([idea], ref=REF)
    row = rows[0]
    assert row["earnings_estimated"] is True
    assert row["bucket"] in set(bucket_names()) | {BEYOND}
    assert row["earnings_date"] is not None


def test_index_states_the_estimate_and_discovery_is_recursive(isolate_roots, monkeypatch):
    _no_network(monkeypatch, ["2026-05-05", "2026-02-04", "2025-11-05", "2025-08-06"])
    ideas = [
        _idea("ACLS", "Information Technology", Side.LONG, (REF + timedelta(days=10)).isoformat()),
        _idea("ABT", "Health Care", Side.SHORT, "2026-05-05"),
    ]
    for idea in ideas:
        md, js = idea_paths(idea, day="2026-08-18", ref=REF)
        md.write_text("# idea\n", encoding="utf-8")
        js.write_text("{}", encoding="utf-8")

    rows = placements(ideas, ref=REF)
    assert set(group_by_sector(rows)) == {"Information-Technology", "Health-Care"}
    assert all(b in set(bucket_names()) | {BEYOND} for b in group_by_bucket(rows))

    index = write_index(rows, day="2026-08-18")
    text = index.read_text(encoding="utf-8")
    assert "calendar days" in text
    assert "*(est.)*" in text
    assert "no future earnings date published" in text
    assert "long_ACLS" in text

    day_folder = index.parent
    assert len(find_idea_files(day_folder)) == 2
    assert find_idea_markdown(day_folder, "short", "ABT") is not None
    assert find_idea_markdown(day_folder, "short", "NOPE") is None


def test_bucket_measured_from_pinned_run_date(isolate_roots, monkeypatch):
    _no_network(monkeypatch, [])
    from ptm.asof import set_as_of

    set_as_of("2026-07-20")
    try:
        pinned_ref = date(2026, 7, 20)
        idea = _idea("AAA", "Industrials", Side.LONG, (pinned_ref + timedelta(days=5)).isoformat())
        row = placements([idea])[0]
        assert row["days_to_earnings"] == 5
        assert row["bucket"] == "00-30d"
    finally:
        set_as_of(None)


def test_every_earnings_date_is_marked_estimated(isolate_roots, monkeypatch):
    """EDGAR publishes no forward earnings calendar, so every date is a
    projection. Labelling one 'published' would misrepresent its provenance."""
    from ptm.earnings import resolve

    _no_network(monkeypatch, ["2026-05-05", "2026-02-04", "2025-11-05", "2025-08-06"])
    est = resolve("ABT", None, ref=REF)
    assert est.estimated is True
    assert est.last_report == "2026-05-05"
    assert est.date > REF.isoformat()
    assert "no future earnings date published" in est.basis
    assert "cadence" in est.basis


def test_pipeline_does_not_relabel_a_projection_as_published(isolate_roots, monkeypatch):
    """Regression: the pipeline used to read the already-projected date out of
    the fundamentals table, where a future date looks indistinguishable from a
    published one, and every idea came out estimated=False."""
    from ptm.earnings import resolve

    _no_network(monkeypatch, ["2026-05-05", "2026-02-04", "2025-11-05"])
    projected = resolve("ABT", None, ref=REF)
    # Feeding that projection back in as if it were a published date is the bug.
    round_tripped = resolve("ABT", projected.date, ref=REF)
    assert round_tripped.estimated is False, "sanity: a future raw date reads as published"
    # Which is why the pipeline must pass None and let this module project.
    import inspect

    from ptm import pipeline

    source = inspect.getsource(pipeline.generate_ideas)
    assert "resolve_earnings(cand.ticker, None" in source
