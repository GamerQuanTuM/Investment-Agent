from datetime import date, timedelta

import pytest

from investment_agent.portfolio.calculations import calculate_sip_future_value
from investment_agent.portfolio.fund_metrics import (
    calculate_xirr,
    expense_ratio_drag,
    ltcg_stcg_estimate,
    project_sip,
    rolling_return_extremes,
    sip_backtest,
    trailing_cagr,
)

# --- calculate_xirr -----------------------------------------------------------------


def test_calculate_xirr_simple_annual_return():
    # -1000 today, +1100 in exactly 1 year -> textbook 10% IRR.
    cash_flows = [(date(2020, 1, 1), -1000.0), (date(2021, 1, 1), 1100.0)]
    assert calculate_xirr(cash_flows) == pytest.approx(10.0, abs=0.3)


def test_calculate_xirr_zero_net_return_is_zero_regardless_of_timing():
    # 12 monthly -100 outflows summing to exactly the +1200 inflow: NPV(0) = sum(amounts) =
    # 0 exactly, so r=0 is an exact root no matter how the cash flows are spaced in time.
    cash_flows = [(date(2020, m, 1), -100.0) for m in range(1, 13)]
    cash_flows.append((date(2021, 1, 1), 1200.0))
    assert calculate_xirr(cash_flows) == pytest.approx(0.0, abs=0.1)


def test_calculate_xirr_degenerate_inputs_return_none():
    assert calculate_xirr([(date(2020, 1, 1), -100.0)]) is None  # fewer than 2 flows
    assert calculate_xirr([(date(2020, 1, 1), -100.0), (date(2020, 2, 1), -50.0)]) is None  # all same sign


# --- trailing_cagr --------------------------------------------------------------------


def test_trailing_cagr_exact_one_year_window():
    nav_history = [  # newest-first, matching mfapi.in's own ordering
        {"date": "2026-01-01", "nav": 121.0},
        {"date": "2025-06-01", "nav": 115.0},
        {"date": "2025-01-01", "nav": 110.0},
    ]
    # 121 / 110 - 1 = 10.0%
    assert trailing_cagr(nav_history, years=1) == pytest.approx(10.0, abs=0.01)


def test_trailing_cagr_insufficient_history_is_none():
    nav_history = [{"date": "2026-01-01", "nav": 100.0}]
    assert trailing_cagr(nav_history, years=5) is None


# --- sip_backtest -----------------------------------------------------------------------


def test_sip_backtest_on_flat_nav_has_zero_xirr():
    # Flat NAV of 100 for all 3 monthly installments: invested == current value exactly
    # (no growth at all), so XIRR must be 0% regardless of installment timing.
    nav_history = [
        {"date": "2025-03-01", "nav": 100.0},
        {"date": "2025-02-01", "nav": 100.0},
        {"date": "2025-01-01", "nav": 100.0},
    ]
    result = sip_backtest(nav_history, monthly_amount=1000.0, start_date=date(2025, 1, 1))
    assert result["invested"] == 3000.0
    assert result["units"] == pytest.approx(30.0)
    assert result["current_value"] == 3000.0
    assert result["xirr_pct"] == pytest.approx(0.0, abs=0.1)
    assert result["start_date"] == "2025-01-01"
    assert result["end_date"] == "2025-03-01"


def test_sip_backtest_rising_nav_has_positive_xirr_and_fewer_units_later():
    nav_history = [
        {"date": "2025-03-01", "nav": 120.0},
        {"date": "2025-02-01", "nav": 110.0},
        {"date": "2025-01-01", "nav": 100.0},
    ]
    result = sip_backtest(nav_history, monthly_amount=1000.0, start_date=date(2025, 1, 1))
    assert result["invested"] == 3000.0
    # units = 1000/100 + 1000/110 + 1000/120 < 30 (first installment alone bought 10 units)
    assert result["units"] < 30.0
    assert result["current_value"] > result["invested"]
    assert result["xirr_pct"] is not None
    assert result["xirr_pct"] > 0.0


def test_sip_backtest_start_after_latest_nav_is_data_unavailable():
    nav_history = [{"date": "2025-01-01", "nav": 100.0}]
    result = sip_backtest(nav_history, monthly_amount=1000.0, start_date=date(2026, 1, 1))
    assert result == {
        "invested": None,
        "units": None,
        "current_value": None,
        "xirr_pct": None,
        "start_date": None,
        "end_date": None,
    }


def test_sip_backtest_step_up_increases_amount_after_12_installments():
    # 13 distinct first-of-month dates, flat NAV, so the 13th installment (index 12)
    # triggers exactly one step-up.
    dates = []
    y, m = 2025, 1
    for _ in range(13):
        dates.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    nav_history = [{"date": d.isoformat(), "nav": 100.0} for d in reversed(dates)]

    result = sip_backtest(nav_history, monthly_amount=1000.0, start_date=dates[0], step_up_pct=10.0)
    # 12 installments at 1000 + 1 installment at 1100 (stepped up on the 13th) = 13100.
    assert result["invested"] == 13100.0


# --- rolling_return_extremes -------------------------------------------------------------


def test_rolling_return_extremes_constant_growth_has_equal_best_and_worst():
    annual_rate = 0.10
    points = []
    start = date(2015, 1, 1)
    for i in range(73):  # ~6 years of monthly points
        d = start + timedelta(days=30 * i)
        value = 100.0 * (1 + annual_rate) ** (i / 12.0)
        points.append({"date": d.isoformat(), "nav": round(value, 6)})
    nav_history = list(reversed(points))  # newest-first

    result = rolling_return_extremes(nav_history, window_years=3.0)
    assert result["best_pct"] == pytest.approx(10.0, abs=1.0)
    assert result["worst_pct"] == pytest.approx(10.0, abs=1.0)


def test_rolling_return_extremes_insufficient_history_is_none():
    nav_history = [{"date": "2026-01-01", "nav": 100.0}, {"date": "2025-01-01", "nav": 100.0}]
    result = rolling_return_extremes(nav_history, window_years=3.0)
    assert result == {"best_pct": None, "worst_pct": None}


# --- project_sip ----------------------------------------------------------------------------


def test_project_sip_without_step_up_matches_existing_sip_formula():
    result = project_sip(1000.0, 3, 12.0, step_up_pct=0.0, inflation_pct=0.0)
    expected = calculate_sip_future_value(1000.0, 12.0, 3)
    assert result["nominal_corpus"] == expected
    assert result["invested"] == 36000.0
    # No inflation requested -> inflation-adjusted equals nominal.
    assert result["inflation_adjusted_corpus"] == expected


def test_project_sip_inflation_adjustment_at_zero_return():
    # 0% return -> nominal corpus is just the sum invested; inflation-adjusted divides by
    # (1 + inflation)^years.
    result = project_sip(1000.0, 1, 0.0, step_up_pct=0.0, inflation_pct=10.0)
    assert result["nominal_corpus"] == 12000.0
    assert result["inflation_adjusted_corpus"] == pytest.approx(10909.09, abs=0.1)


def test_project_sip_step_up_grows_more_than_flat():
    flat = project_sip(1000.0, 5, 10.0, step_up_pct=0.0)
    stepped = project_sip(1000.0, 5, 10.0, step_up_pct=10.0)
    assert stepped["invested"] > flat["invested"]
    assert stepped["nominal_corpus"] > flat["nominal_corpus"]


# --- ltcg_stcg_estimate ----------------------------------------------------------------------


def test_ltcg_stcg_estimate_debt_fund_refuses_to_guess():
    result = ltcg_stcg_estimate(gains=100000.0, holding_period_years=5.0, is_equity=False)
    assert result["tax"] is None
    assert result["tax_type"] == "DATA_UNAVAILABLE"


def test_ltcg_stcg_estimate_no_gain_is_no_tax():
    result = ltcg_stcg_estimate(gains=0.0, holding_period_years=5.0)
    assert result == {"tax": 0.0, "tax_type": "NONE", "rate_pct": 0.0, "note": "No gain, no tax."}


def test_ltcg_stcg_estimate_long_term_applies_exemption():
    # Gains of 2,00,000 over 2 years (equity, >=1y): taxable = 200000 - 125000 = 75000;
    # tax = 75000 * 12.5% = 9375.0
    result = ltcg_stcg_estimate(gains=200000.0, holding_period_years=2.0)
    assert result["tax_type"] == "LTCG"
    assert result["rate_pct"] == 12.5
    assert result["exemption_used"] == 125000.0
    assert result["tax"] == 9375.0


def test_ltcg_stcg_estimate_short_term_has_no_exemption():
    # Gains of 1,00,000 held 6 months (equity, <1y): tax = 100000 * 20% = 20000.0, no exemption.
    result = ltcg_stcg_estimate(gains=100000.0, holding_period_years=0.5)
    assert result["tax_type"] == "STCG"
    assert result["rate_pct"] == 20.0
    assert result["exemption_used"] == 0.0
    assert result["tax"] == 20000.0


# --- expense_ratio_drag ----------------------------------------------------------------------


def test_expense_ratio_drag_direct_plan_beats_regular():
    result = expense_ratio_drag(10000.0, 10, 12.0, ter_regular_pct=1.5, ter_direct_pct=0.5)
    assert result["corpus_direct"] > result["corpus_regular"]
    assert result["savings_from_direct"] > 0
    assert result["savings_from_direct"] == round(result["corpus_direct"] - result["corpus_regular"], 2)


def test_expense_ratio_drag_identical_ter_has_zero_savings():
    result = expense_ratio_drag(10000.0, 10, 12.0, ter_regular_pct=1.0, ter_direct_pct=1.0)
    assert result["savings_from_direct"] == 0.0
