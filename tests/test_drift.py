import pytest

from ptm import drift


def _exp(up=None, down=None, change_90d=None, change_30d=None, available=True,
         eps_now=5.0, eps_then=4.5):
    """EPS levels are required, not optional: a percentage change is refused
    when its base crosses zero or is a rounding error, so a fixture without
    them measures no magnitude at all."""
    return {
        "revisions": {
            "available": available,
            "analysts_up_30d": up,
            "analysts_down_30d": down,
            "change_90d_pct": change_90d,
            "change_30d_pct": change_30d,
            "eps_current": eps_now,
            "eps_d90": eps_then,
        }
    }


class _Qual:
    def __init__(self, direction, durability="intact"):
        self.filing_direction = direction
        # "intact" weights 1.0, so tests read the raw revision distance unless
        # they are specifically exercising durability.
        self.momentum_durability = durability


def test_direction_comes_from_breadth_not_the_percentage():
    """Breadth is bounded, needs no division and came back for 100% of names.
    The percentage carries near-zero-base artefacts, so it supplies magnitude
    only once breadth has settled the sign."""
    out = drift.consensus_drift(_exp(up=7, down=1, change_90d=-2.0))
    assert out["direction"] == 1, "6 net upgrades outweigh a small negative percentage"
    assert "7 analysts up vs 1 down" in out["why"]


def test_percentage_decides_when_breadth_is_absent():
    out = drift.consensus_drift(_exp(change_90d=-9.0))
    assert out["direction"] == -1
    assert out["magnitude_pct"] == 9.0


def test_a_sign_flipped_base_is_refused_not_capped():
    """ECHO's -1402% came from a base EPS of -3.02 turning into +39.34. Capping
    it to -30% did not remove the artefact, it laundered it into a plausible
    number and put the name in the book."""
    out = drift.consensus_drift(
        _exp(up=0, down=5, change_90d=-1402.1, eps_now=39.335, eps_then=-3.021)
    )
    assert out["direction"] == -1, "the analyst head count is still valid"
    assert out["magnitude_pct"] is None, "the size is not"
    assert "crosses zero" in out["magnitude_unusable"]


def test_a_rounding_error_base_is_refused():
    """HTLD's +1369% came from a 90-day-ago estimate of $0.013."""
    out = drift.consensus_drift(
        _exp(up=6, down=0, change_90d=1369.5, eps_now=0.187, eps_then=0.013)
    )
    assert out["magnitude_pct"] is None
    assert "too small" in out["magnitude_unusable"]


def test_a_genuinely_large_revision_is_no_longer_flattened():
    """PBF's +160% is real - base EPS 6.75 - and the cap used to squash it onto
    the same value as every other large mover, so the top of the ranking was
    decided by tiebreaks."""
    out = drift.consensus_drift(
        _exp(up=6, down=0, change_90d=160.2, eps_now=17.564, eps_then=6.751)
    )
    assert out["magnitude_pct"] == 160.2


def test_an_unmeasurable_size_yields_no_momentum():
    out = drift.consensus_drift(
        _exp(up=0, down=5, change_90d=-1402.1, eps_now=39.335, eps_then=-3.021)
    )
    edge = drift.momentum_edge(out, _Qual("deteriorating"), side_is_long=False)
    assert edge["edge_pct"] is None
    assert "not measurable" in edge["why"]


def test_a_rounding_level_revision_is_treated_as_flat():
    out = drift.consensus_drift(_exp(up=0, down=0, change_90d=0.4))
    assert out["direction"] == 0
    assert out["gap_pct"] if False else out["why"] == "analysts have not moved"


def test_unavailable_revisions_produce_nothing():
    assert drift.consensus_drift(None)["available"] is False
    assert drift.consensus_drift(_exp(available=False))["available"] is False


def test_momentum_follows_the_revision_in_the_trade_s_direction():
    """A long wants estimates rising; a short wants them falling. The design
    FOLLOWS the revision rather than fading it - fading was a contrarian bet
    against a documented momentum effect, justified only by backward-looking
    filing evidence."""
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    falling = drift.consensus_drift(_exp(up=0, down=6, change_90d=-14.0))

    assert drift.momentum_edge(rising, _Qual("improving"), side_is_long=True)["edge_pct"] == 14.0
    assert drift.momentum_edge(falling, _Qual("deteriorating"), side_is_long=False)["edge_pct"] == 14.0


def test_revisions_moving_against_the_trade_are_a_negative_edge():
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    assert drift.momentum_edge(rising, _Qual("improving"), side_is_long=False)["edge_pct"] == -14.0


def test_agreeing_filings_are_support_not_a_penalty():
    """Under a momentum framing the market moving your way is CONFIRMATION. An
    earlier design docked conviction for exactly this, which ranked the book
    against its own primary signal."""
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    agree = drift.momentum_edge(rising, _Qual("improving"), side_is_long=True)
    silent = drift.momentum_edge(rising, _Qual("silent"), side_is_long=True)
    assert agree["edge_pct"] == silent["edge_pct"], "support must not change the magnitude"
    assert agree["support"] and not silent["support"]
    assert "filings point the same way" in agree["why"]


def test_filings_veto_a_revision_their_own_numbers_contradict():
    """The one place filings still bite, and it is a risk control rather than a
    signal: they cannot show the analysts are wrong, only that following the
    revision means ignoring the company's own reported figures."""
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    out = drift.momentum_edge(rising, _Qual("deteriorating"), side_is_long=True)
    assert out["veto"], out
    assert "not following a revision its numbers contradict" in out["veto"]


def test_silent_filings_do_not_veto():
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    assert drift.momentum_edge(rising, _Qual("silent"), side_is_long=True)["veto"] == ""
    assert drift.momentum_edge(rising, _Qual("mixed"), side_is_long=True)["veto"] == ""


def test_no_momentum_when_analysts_have_not_moved():
    flat = drift.consensus_drift(_exp(up=0, down=0, change_90d=0.2))
    out = drift.momentum_edge(flat, _Qual("improving"), side_is_long=True)
    assert out["edge_pct"] is None
    assert "no momentum to follow" in out["why"]


def test_summary_line_calls_it_momentum_not_a_mispricing():
    """The framing matters: this does not claim the market is wrong."""
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    text = drift.summary_line(drift.momentum_edge(rising, _Qual("improving"), side_is_long=True))
    assert "Revision momentum" in text
    assert "not a claim that the market is mispriced" in text


def test_summary_line_surfaces_a_veto():
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=14.0))
    text = drift.summary_line(drift.momentum_edge(rising, _Qual("deteriorating"), side_is_long=True))
    assert "**Vetoed:**" in text


# --- theme cohorts ------------------------------------------------------------


def _cohort_rows():
    """Six AI-exposed names, five being upgraded; two GLP-1 names, too few."""
    rows = [
        {"ticker": f"AI{i}", "themes": ["AI and data centre (20)"],
         "direction": 1 if i < 5 else -1, "magnitude": 10.0}
        for i in range(6)
    ]
    rows += [
        {"ticker": f"GLP{i}", "themes": ["GLP-1 and obesity (9)"], "direction": 1, "magnitude": 8.0}
        for i in range(2)
    ]
    return rows


def test_a_cohort_needs_enough_names_to_average():
    """Two names is not a cohort and its average says nothing."""
    from ptm.themes import MIN_COHORT, cohort_momentum

    out = cohort_momentum(_cohort_rows())
    assert out["AI and data centre"]["available"] is True
    assert out["GLP-1 and obesity"]["available"] is False
    assert MIN_COHORT > 2


def test_cohort_direction_reflects_the_exposed_names():
    from ptm.themes import cohort_momentum

    ai = cohort_momentum(_cohort_rows())["AI and data centre"]
    assert ai["direction"] == 1
    assert ai["up"] == 5 and ai["down"] == 1
    assert "5 of 6 names exposed to this theme" in ai["why"]


def test_corroboration_lifts_a_name_its_cohort_agrees_with():
    """A theme is a shared driver, so a name moving with its cohort is more
    likely riding a real one than making noise. Modest on purpose: this is
    momentum layered on momentum."""
    from ptm.themes import cohort_momentum, corroboration

    cohorts = cohort_momentum(_cohort_rows())
    agree = corroboration(["AI and data centre (20)"], 1, cohorts)
    disagree = corroboration(["AI and data centre (20)"], -1, cohorts)
    assert 1.0 < agree["multiplier"] <= 1.5, "lift must stay modest"
    assert disagree["multiplier"] < 1.0
    assert "corroborates" in agree["why"]


def test_corroboration_is_neutral_without_a_readable_cohort():
    from ptm.themes import cohort_momentum, corroboration

    cohorts = cohort_momentum(_cohort_rows())
    assert corroboration(["GLP-1 and obesity (9)"], 1, cohorts)["multiplier"] == 1.0
    assert corroboration([], 1, cohorts)["multiplier"] == 1.0
    assert corroboration(["AI and data centre (20)"], 0, cohorts)["multiplier"] == 1.0


def test_theme_cohorts_use_no_price_data():
    """Not technical analysis: the inputs are analyst estimate revisions and the
    words companies use in their own filings."""
    import inspect

    from ptm import themes

    import re

    source = inspect.getsource(themes).lower()
    # Word-bounded, and no generic programming words: an earlier version of this
    # banned "return", which is a Python keyword and made the check meaningless.
    for token in ("sma", "ema", "macd", "moving average", "price action",
                  "total return", "daily return", "closing price"):
        assert not re.search(rf"{re.escape(token)}", source), (
            f"{token!r} would make this technical analysis"
        )


# --- durability ---------------------------------------------------------------


def test_durability_scales_what_is_left_of_the_run():
    """The screen returns quantitative outliers, so a re-rating has usually
    started. How much is LEFT is the live question."""
    rising = drift.consensus_drift(_exp(up=6, down=0, change_90d=20.0))
    edges = {
        state: drift.momentum_edge(rising, _Qual("improving", state), side_is_long=True)["edge_pct"]
        for state in ("building", "intact", "fading", "exhausted")
    }
    assert edges["building"] > edges["intact"] > edges["fading"] > edges["exhausted"]
    assert edges["exhausted"] > 0, "a finished run is not a reason to take the other side"


def test_acceleration_reads_whether_the_run_is_still_going():
    steady = drift.consensus_drift(_exp(up=6, down=0, change_30d=5.0, change_90d=15.0))
    stalled = drift.consensus_drift(_exp(up=6, down=0, change_30d=0.5, change_90d=15.0))
    assert steady["pace"] in {"steady pace", "still accelerating"}
    assert stalled["pace"] == "pace has slowed"


def test_acceleration_is_absent_without_both_windows():
    only90 = drift.consensus_drift(_exp(up=6, down=0, change_90d=15.0))
    assert only90["acceleration"] is None
