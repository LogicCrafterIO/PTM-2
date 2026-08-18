from ptm.formulas import (
    atrp,
    bear_level,
    earnings_growth,
    enterprise_value,
    pe,
    peg,
    r_score,
    slope_beta,
    true_range_pct,
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


def test_atrp_and_r():
    tr = true_range_pct(12, 10, 11, 10)
    assert tr is not None and tr > 0
    assert abs(atrp([0.1, 0.1, 0.1]) - 0.1) < 1e-9
    assert r_score(0.24, 0.08) == 3


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
