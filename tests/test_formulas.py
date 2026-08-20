from ptm.formulas import (
    bear_level,
    earnings_growth,
    enterprise_value,
    pe,
    peg,
    slope_beta,
)


def test_eg_sign_changes():
    assert earnings_growth(-1.0, 2.0) == -1.0
    assert earnings_growth(2.0, -1.0) == 1.0
    assert abs(earnings_growth(1.2, 1.0) - 0.2) < 1e-9


def test_pe_peg():
    assert pe(10, 1) == 10
    assert pe(10, -1) is None
    assert abs(peg(20, 0.20) - 1.0) < 1e-9
    assert peg(20, -0.1) is None


def test_bear_level():
    assert bear_level(100) == 80


def test_atr_and_r_score_helpers_are_gone():
    """Deleted with the move to options: a stop distance on the underlying does
    not manage a defined-risk position, and none of these gated anything."""
    import ptm.formulas as formulas

    for name in ("true_range_pct", "atrp", "r_score", "close_to_close", "high_to_low"):
        assert not hasattr(formulas, name), f"{name} should have been removed"


def test_eg_zero_and_negative_prev():
    assert earnings_growth(0.0, 0.0) == 0.0
    assert earnings_growth(1.0, 0.0) == 1.0
    assert earnings_growth(-1.0, 0.0) == -1.0


def test_enterprise_value_and_beta():
    assert enterprise_value(100, 20, 5) == 115
    y = [0.01, 0.02, -0.01, 0.00, 0.03, 0.01, -0.02, 0.02, 0.01, 0.00, 0.01, 0.02]
    x = [v * 0.5 for v in y]
    beta = slope_beta(y, x)
    assert beta is not None and beta > 0
