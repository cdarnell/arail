"""Pure-arithmetic tests for Consolidation Analyzer.

Per ARCHITECTURE.md §5.2/§7.5 and the test strategy §11: hand-computed
reference values for at least 3 scenarios (single debt, multi-debt
avalanche-shaped, transfer-fee breakeven).
"""

from __future__ import annotations

import math

from arail.agents._builtin_consolidation_analyzer import (
    ScenarioResult,
    blended_apr,
    breakeven_months,
    monthly_interest_cost,
    threshold_crossings,
)


# ── blended_apr ───────────────────────────────────────────────────────

def test_blended_apr_single_debt_equals_its_own_apr():
    debts = [{"balance": 5000.0, "apr": 22.0}]
    assert blended_apr(debts) == 22.0


def test_blended_apr_multi_debt_hand_computed():
    # weighted: (1000*20 + 3000*10) / 4000 = (20000 + 30000) / 4000 = 12.5
    debts = [{"balance": 1000.0, "apr": 20.0}, {"balance": 3000.0, "apr": 10.0}]
    assert blended_apr(debts) == 12.5


def test_blended_apr_zero_total_balance_is_none():
    assert blended_apr([{"balance": 0.0, "apr": 20.0}]) is None
    assert blended_apr([]) is None


# ── monthly_interest_cost ───────────────────────────────────────────────

def test_monthly_interest_cost_hand_computed():
    # 1000 * 0.20 / 12 = 16.666...
    assert math.isclose(monthly_interest_cost(1000.0, 20.0), 16.6666666, rel_tol=1e-5)


def test_monthly_interest_cost_zero_apr_is_zero():
    assert monthly_interest_cost(1000.0, 0.0) == 0.0


# ── breakeven_months ────────────────────────────────────────────────────

def test_breakeven_hand_computed_transfer_fee_scenario():
    # $150 fee, $30/month savings -> 5 months, rounded up.
    assert breakeven_months(150.0, 30.0) == 5

    # $151 fee, $30/month savings -> rounds up to 6.
    assert breakeven_months(151.0, 30.0) == 6


def test_breakeven_no_savings_never_breaks_even():
    assert breakeven_months(150.0, 0.0) is None
    assert breakeven_months(150.0, -5.0) is None


def test_breakeven_zero_fee_breaks_even_immediately():
    assert breakeven_months(0.0, 30.0) == 0


# ── threshold_crossings (Workstream C: pure comparison, no I/O) ────────

def _result(institution="PenFed Credit Union", product="balance-transfer",
            breakeven=None):
    return ScenarioResult(
        institution=institution, product=product, rate=5.0, fee_pct=3.0,
        source="https://example.com", as_of="2026-08-01",
        fee_amount=100.0, new_monthly_interest=10.0, monthly_savings=20.0,
        breakeven=breakeven,
    )


def test_no_threshold_set_means_no_crossings():
    results = [_result(breakeven=6)]
    assert threshold_crossings({}, results, None) == []


def test_first_time_below_threshold_is_a_crossing():
    results = [_result(breakeven=6)]
    crossed = threshold_crossings({}, results, alert_breakeven_months=12)
    assert crossed == ["PenFed Credit Union|balance-transfer"]


def test_already_below_threshold_last_tick_is_not_a_new_crossing():
    key = "PenFed Credit Union|balance-transfer"
    prev = {key: {"breakeven": 6}}
    results = [_result(breakeven=5)]  # still below, was already below
    assert threshold_crossings(prev, results, alert_breakeven_months=12) == []


def test_moving_above_threshold_is_not_a_crossing():
    key = "PenFed Credit Union|balance-transfer"
    prev = {key: {"breakeven": 6}}
    results = [_result(breakeven=18)]  # now above the threshold
    assert threshold_crossings(prev, results, alert_breakeven_months=12) == []


def test_never_breaks_even_is_never_a_crossing():
    results = [_result(breakeven=None)]
    assert threshold_crossings({}, results, alert_breakeven_months=12) == []


def test_multiple_scenarios_only_crossing_ones_reported():
    results = [
        _result(institution="PenFed Credit Union", breakeven=6),
        _result(institution="Navy Federal Credit Union", breakeven=24),
    ]
    crossed = threshold_crossings({}, results, alert_breakeven_months=12)
    assert crossed == ["PenFed Credit Union|balance-transfer"]
