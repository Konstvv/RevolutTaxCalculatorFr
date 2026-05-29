"""Tests for the FIFO portfolio tracker."""

from datetime import date

import pytest

from revolut_tax_fr.portfolio import Portfolio

D = date.fromisoformat


def test_single_buy_sell_eur():
    p = Portfolio()
    p.buy("AA", D("2020-01-01"), quantity=2, total_amount=200.0, fx_rate=1.0)
    cost, proceeds = p.sell("AA", quantity_sold=2, total_amount=240.0, fx_rate=1.0)
    assert cost == pytest.approx(200.0)
    assert proceeds == pytest.approx(240.0)


def test_single_buy_sell_usd():
    """Uses total_amount (actual charged/received including spread), not price*qty."""
    p = Portfolio()
    # Fictional example: bought for $100.00 (incl. spread), sold for $120.00, FX 1.20
    p.buy("FOO", D("2020-01-15"), quantity=2, total_amount=100.00, fx_rate=1.20)
    cost, proceeds = p.sell("FOO", quantity_sold=2, total_amount=120.00, fx_rate=1.20)

    assert cost == pytest.approx(100.00 / 1.20, rel=1e-4)
    assert proceeds == pytest.approx(120.00 / 1.20, rel=1e-4)
    # gain = (120 - 100) / 1.20 = 16.67
    assert (proceeds - cost) == pytest.approx(20.00 / 1.20, abs=0.02)


def test_fifo_order():
    """Oldest lot is consumed first."""
    p = Portfolio()
    p.buy("BAR", D("2020-01-01"), quantity=1, total_amount=90.0, fx_rate=1.0)  # lot A
    p.buy("BAR", D("2020-06-01"), quantity=1, total_amount=100.0, fx_rate=1.0)  # lot B

    # Sell 1 share → should consume lot A (cost €90), not lot B (cost €100)
    cost, _ = p.sell("BAR", quantity_sold=1, total_amount=110.0, fx_rate=1.0)
    assert cost == pytest.approx(90.0)

    # Remaining lot is B
    cost2, _ = p.sell("BAR", quantity_sold=1, total_amount=110.0, fx_rate=1.0)
    assert cost2 == pytest.approx(100.0)


def test_partial_lot_consumption():
    p = Portfolio()
    p.buy("BAZ", D("2020-01-01"), quantity=5, total_amount=250.0, fx_rate=1.0)

    cost, _ = p.sell("BAZ", quantity_sold=2, total_amount=120.0, fx_rate=1.0)
    assert cost == pytest.approx(100.0)  # 2/5 of 250

    cost2, _ = p.sell("BAZ", quantity_sold=3, total_amount=180.0, fx_rate=1.0)
    assert cost2 == pytest.approx(150.0)  # 3/5 of 250


def test_fractional_shares():
    """Fractional quantities are supported; negative sell proceeds are floored to zero."""
    p = Portfolio()
    p.buy("DLST", D("2020-03-01"), quantity=5.5, total_amount=31.0, fx_rate=1.10)

    cost, proceeds = p.sell("DLST", quantity_sold=5.5, total_amount=-0.01, fx_rate=1.10)
    # Negative total_amount (delisted/worthless stock) is floored to 0 proceeds
    assert proceeds == pytest.approx(0.0, abs=1e-6)
    assert cost == pytest.approx(31.0 / 1.10, rel=1e-4)


def test_negative_total_amount_floored_to_zero():
    """Worthless stock sell with negative total_amount → zero proceeds."""
    p = Portfolio()
    p.buy("DEAD", D("2020-01-01"), quantity=10, total_amount=50.0, fx_rate=1.0)
    _, proceeds = p.sell("DEAD", quantity_sold=10, total_amount=-0.05, fx_rate=1.0)
    assert proceeds == pytest.approx(0.0)


def test_fifo_underflow_raises():
    p = Portfolio()
    with pytest.raises(ValueError, match="FIFO underflow"):
        p.sell("NONE", quantity_sold=1, total_amount=100.0, fx_rate=1.0)


def test_cross_ticker_isolation():
    p = Portfolio()
    p.buy("XX", D("2020-01-01"), quantity=1, total_amount=150.0, fx_rate=1.0)
    p.buy("YY", D("2020-01-01"), quantity=1, total_amount=130.0, fx_rate=1.0)

    cost_xx, _ = p.sell("XX", quantity_sold=1, total_amount=160.0, fx_rate=1.0)
    cost_yy, _ = p.sell("YY", quantity_sold=1, total_amount=140.0, fx_rate=1.0)

    assert cost_xx == pytest.approx(150.0)
    assert cost_yy == pytest.approx(130.0)
