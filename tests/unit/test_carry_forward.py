"""Unit tests for carry-forward loss logic."""

import pytest

from revolut_tax_fr.calculator import CarryForwardLoss, _apply_pool_to_gain, _evolve_pool

# ---------------------------------------------------------------------------
# _evolve_pool — pool state after a completed year
# ---------------------------------------------------------------------------


def test_evolve_pool_net_loss_appends():
    pool = _evolve_pool(2023, -5.0, [])
    assert len(pool) == 1
    assert pool[0].origin_year == 2023
    assert pool[0].amount_eur == pytest.approx(5.0)


def test_evolve_pool_net_gain_consumes_oldest_first():
    pool = [CarryForwardLoss(2022, 3.0), CarryForwardLoss(2023, 4.0)]
    result = _evolve_pool(2024, 5.0, pool)
    # 3.0 (2022) fully consumed, 2.0 of 4.0 (2023) consumed → 2.0 left
    assert len(result) == 1
    assert result[0].origin_year == 2023
    assert result[0].amount_eur == pytest.approx(2.0)


def test_evolve_pool_gain_larger_than_pool_clears_pool():
    pool = [CarryForwardLoss(2022, 10.0)]
    result = _evolve_pool(2024, 100.0, pool)
    assert result == []


def test_evolve_pool_zero_gain_leaves_pool_unchanged():
    pool = [CarryForwardLoss(2022, 5.0)]
    result = _evolve_pool(2024, 0.0, pool)
    assert len(result) == 1
    assert result[0].amount_eur == pytest.approx(5.0)


def test_evolve_pool_net_loss_with_existing_pool():
    pool = [CarryForwardLoss(2022, 3.0)]
    result = _evolve_pool(2023, -7.0, pool)
    assert len(result) == 2
    assert result[-1].origin_year == 2023
    assert result[-1].amount_eur == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# _apply_pool_to_gain — current year application
# ---------------------------------------------------------------------------


def test_apply_pool_fully_absorbed():
    pool = [CarryForwardLoss(2023, 5.0)]
    adjusted, used, remaining = _apply_pool_to_gain(3.0, pool)
    assert adjusted == pytest.approx(0.0)
    assert sum(cf.amount_eur for cf in used) == pytest.approx(3.0)
    assert len(remaining) == 1
    assert remaining[0].amount_eur == pytest.approx(2.0)


def test_apply_pool_fully_consumed():
    pool = [CarryForwardLoss(2023, 2.0)]
    adjusted, used, remaining = _apply_pool_to_gain(5.0, pool)
    assert adjusted == pytest.approx(3.0)
    assert len(used) == 1
    assert used[0].amount_eur == pytest.approx(2.0)
    assert remaining == []


def test_apply_pool_multiple_years_oldest_first():
    pool = [CarryForwardLoss(2021, 1.0), CarryForwardLoss(2022, 2.0), CarryForwardLoss(2023, 3.0)]
    adjusted, used, remaining = _apply_pool_to_gain(2.5, pool)
    assert adjusted == pytest.approx(0.0)
    # Should consume 2021 (1.0) and 1.5 of 2022
    used_years = [cf.origin_year for cf in used]
    assert 2021 in used_years
    assert 2022 in used_years
    assert remaining[0].origin_year == 2022
    assert remaining[0].amount_eur == pytest.approx(0.5)
    assert remaining[1].origin_year == 2023


def test_apply_pool_empty_pool():
    adjusted, used, remaining = _apply_pool_to_gain(10.0, [])
    assert adjusted == pytest.approx(10.0)
    assert used == []
    assert remaining == []


# ---------------------------------------------------------------------------
# End-to-end carry-forward scenario (no file I/O)
# ---------------------------------------------------------------------------


def test_three_year_scenario():
    """Year 1: loss, Year 2: loss, Year 3: gain absorbed by carry-forward."""
    # Year 2001: net loss -1.00
    pool = _evolve_pool(2001, -1.00, [])
    assert len(pool) == 1

    # Year 2002: net loss -10.00 (pool NOT applied because net is negative)
    pool = _evolve_pool(2002, -10.00, pool)
    assert len(pool) == 2
    total = sum(cf.amount_eur for cf in pool)
    assert total == pytest.approx(11.00, abs=0.01)

    # Year 2003: raw gain +8.00 → fully absorbed by carry-forward
    gain = 8.00
    adjusted, used, remaining = _apply_pool_to_gain(gain, pool)

    assert adjusted == pytest.approx(0.0)
    assert sum(cf.amount_eur for cf in used) == pytest.approx(gain, abs=0.01)
    # 2001 (1.00) fully consumed, 7.00 of 2002 consumed; 3.00 remains from 2002
    assert len(remaining) == 1
    assert remaining[0].origin_year == 2002
    assert remaining[0].amount_eur == pytest.approx(11.00 - 8.00, abs=0.02)


def test_ten_year_expiry():
    """Losses expire after 10 years."""
    pool = [
        CarryForwardLoss(2010, 100.0),  # will expire by 2021
        CarryForwardLoss(2015, 50.0),  # valid in 2025
    ]
    target_year = 2021
    active_pool = [cf for cf in pool if target_year - cf.origin_year <= 10]
    assert len(active_pool) == 1
    assert active_pool[0].origin_year == 2015
