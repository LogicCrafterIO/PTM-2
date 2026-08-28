from datetime import date

import pytest

from ptm import asof
from ptm.asof import AsOfUnavailable
from ptm.backdate import next_report_estimate


def test_available_months_are_the_last_three_prints():
    now = date(2026, 8, 18)
    assert [asof.month_label(m) for m in asof.ism_available_months(now)] == [
        "July 2026",
        "June 2026",
        "May 2026",
    ]


def test_earliest_as_of_lands_on_the_oldest_available_print():
    now = date(2026, 8, 18)
    # Oldest live report is May, released early June.
    assert asof.earliest_as_of(now) == date(2026, 6, 4)


@pytest.mark.parametrize(
    "day,report",
    [
        ("2026-08-18", "July 2026"),
        ("2026-07-15", "June 2026"),
        ("2026-06-04", "May 2026"),
    ],
)
def test_supported_backdates_resolve_to_a_published_report(day, report):
    now = date(2026, 8, 18)
    resolved = asof.validate_as_of(day, now=now)
    assert asof.month_label(asof.ism_report_month(resolved)) == report


def test_backdate_before_the_floor_is_refused():
    now = date(2026, 8, 18)
    with pytest.raises(AsOfUnavailable) as exc:
        asof.validate_as_of("2026-05-20", now=now)
    assert "April 2026" in str(exc.value)
    assert "2026-06-04" in str(exc.value)


def test_future_dates_are_refused():
    with pytest.raises(AsOfUnavailable):
        asof.validate_as_of("2026-09-01", now=date(2026, 8, 18))


def test_early_in_the_month_the_prior_print_is_not_out_yet():
    # Aug 1: July's PMI has not been released, so June is the newest print.
    assert asof.ism_report_month(date(2026, 8, 1)) == (2026, 6)
    assert asof.ism_report_month(date(2026, 8, 4)) == (2026, 7)


def test_set_as_of_moves_the_run_date_and_resets():
    asof.set_as_of("2026-06-20")
    try:
        assert asof.as_of_date() == date(2026, 6, 20)
        assert asof.day_slug() == "2026-06-20"
        assert asof.is_backdated() is True
        # days_until measures from the pinned date, not wall clock
        assert asof.days_until("2026-07-10") == 20
    finally:
        asof.set_as_of(None)
    assert asof.is_backdated() is False


def test_next_report_estimate_projects_forward_from_past_filings_only():
    # Filings roughly every 91 days; the run date is 2026-06-20.
    filings = ["2026-05-05", "2026-02-04", "2025-11-05", "2025-08-06"]
    projected, note = next_report_estimate(filings, date(2026, 6, 20))
    assert projected is not None
    assert projected > "2026-06-20"
    assert "cadence" in note


def test_next_report_estimate_ignores_filings_after_the_run_date():
    filings = ["2026-08-05", "2026-05-05", "2026-02-04", "2025-11-05"]
    projected, _ = next_report_estimate(filings, date(2026, 6, 20))
    # The August filing was not public on 2026-06-20 and must not anchor anything.
    assert projected is not None
    assert projected < "2026-08-05"
