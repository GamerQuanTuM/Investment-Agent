import pytest

from investment_agent.portfolio.calculations import (
    calculate_annualized_volatility_pct,
    calculate_cagr,
    calculate_debt_to_equity,
    calculate_distance_from_high_pct,
    calculate_fcf,
    calculate_interest_coverage,
    calculate_max_drawdown,
    calculate_pb_ratio,
    calculate_pe_ratio,
    calculate_percentile_rank,
    calculate_portfolio_weights,
    calculate_return_pct,
    calculate_roce,
    calculate_roe,
    calculate_sector_exposure,
    calculate_sip_future_value,
    derive_ratios_from_statements,
)


def test_calculate_cagr():
    # 100 growing to 200 in 3 years = ~25.99%
    cagr = calculate_cagr(100.0, 200.0, 3.0)
    assert round(cagr, 2) == 25.99

    with pytest.raises(ValueError):
        calculate_cagr(-10.0, 100.0, 3.0)


def test_calculate_pe_ratio():
    pe = calculate_pe_ratio(current_price=2400.0, eps=80.0)
    assert pe == 30.0

    with pytest.raises(ValueError):
        calculate_pe_ratio(2400.0, 0.0)


def test_calculate_pb_ratio():
    pb = calculate_pb_ratio(current_price=1500.0, book_value_per_share=500.0)
    assert pb == 3.0


def test_calculate_debt_to_equity():
    de = calculate_debt_to_equity(total_debt=500.0, total_equity=1000.0)
    assert de == 0.5


def test_calculate_roe_and_roce():
    roe = calculate_roe(net_income=180.0, shareholder_equity=1000.0)
    assert roe == 18.0

    roce = calculate_roce(ebit=250.0, capital_employed=1000.0)
    assert roce == 25.0


def test_calculate_portfolio_weights():
    holdings = {
        "RELIANCE": 50000.0,
        "TCS": 30000.0,
        "HDFCBANK": 20000.0,
    }
    weights = calculate_portfolio_weights(holdings)
    assert weights["RELIANCE"] == 50.0
    assert weights["TCS"] == 30.0
    assert weights["HDFCBANK"] == 20.0


def test_calculate_sector_exposure():
    holdings = [
        {"sector": "IT", "market_value": 40000.0},
        {"sector": "IT", "market_value": 10000.0},
        {"sector": "Financials", "market_value": 50000.0},
    ]
    exposure = calculate_sector_exposure(holdings)
    assert exposure["IT"] == 50.0
    assert exposure["Financials"] == 50.0


def test_calculate_max_drawdown():
    # Peak is 100, drops to 70 -> -30%
    prices = [100.0, 120.0, 110.0, 84.0, 95.0]
    # Peak is 120, trough is 84 -> (84-120)/120 = -36/120 = -30.0%
    dd = calculate_max_drawdown(prices)
    assert dd == -30.0


def test_calculate_sip_future_value():
    # ₹10,000 per month for 3 years at 12% annual return
    # FV formula: 10000 * (((1+0.01)^36 - 1)/0.01) * 1.01 = ~435,076.50
    fv = calculate_sip_future_value(10000.0, 12.0, 3)
    assert 430000 < fv < 440000


def test_calculate_fcf():
    # Operating cash flow 500cr, capex 120cr (given positive, as the caller is told to
    # pass it) -> FCF = 380cr.
    assert calculate_fcf(operating_cash_flow=500.0, capital_expenditure=120.0) == 380.0


def test_derive_ratios_from_statements_happy_path():
    # 4 years of annual statements, newest first (matches Yahoo's ordering), spanning a
    # 3-year CAGR window between the oldest and newest entry.
    statements = {
        "income_statements": [
            {
                "end_date": "2026",
                "total_revenue": 200.0,
                "ebit": 50.0,
                "net_income": 36.0,
                "interest_expense": -10.0,
            },
            {"end_date": "2025", "total_revenue": 170.0, "ebit": 40.0, "net_income": 28.0},
            {"end_date": "2024", "total_revenue": 150.0, "ebit": 32.0, "net_income": 22.0},
            {"end_date": "2023", "total_revenue": 100.0, "ebit": 20.0, "net_income": 18.0},
        ],
        "balance_sheets": [
            {"total_assets": 600.0, "total_current_liabilities": 100.0, "total_equity": 400.0},
        ],
        "cash_flows": [
            {"operating_cash_flow": 80.0, "capex": -20.0},
        ],
    }
    ratios = derive_ratios_from_statements(statements)
    # ROCE = EBIT / (total assets - current liabilities) = 50 / (600 - 100) = 10%
    assert ratios["roce_pct"] == 10.0
    # FCF = OCF - |capex| = 80 - 20 = 60
    assert ratios["fcf"] == 60.0
    # Interest coverage = EBIT / |interest expense| = 50 / 10 = 5.0x
    assert ratios["interest_coverage"] == 5.0
    # Revenue CAGR over 3 periods: 100 -> 200 = 25.99%
    assert ratios["revenue_growth_3y_cagr_pct"] == pytest.approx(25.99, abs=0.01)
    # Profit CAGR over 3 periods: 18 -> 36 = 25.99%
    assert ratios["profit_growth_3y_cagr_pct"] == pytest.approx(25.99, abs=0.01)


def test_derive_ratios_from_statements_missing_data_stays_none():
    # No balance sheet or cash flow entries, and only one income statement year -> every
    # ratio must be None (DATA_UNAVAILABLE), never guessed or defaulted to 0.
    ratios = derive_ratios_from_statements(
        {
            "income_statements": [{"end_date": "2026", "total_revenue": 100.0}],
            "balance_sheets": [],
            "cash_flows": [],
        }
    )
    assert ratios == {
        "roce_pct": None,
        "fcf": None,
        "interest_coverage": None,
        "revenue_growth_3y_cagr_pct": None,
        "profit_growth_3y_cagr_pct": None,
    }


def test_calculate_interest_coverage():
    assert calculate_interest_coverage(ebit=100.0, interest_expense=20.0) == 5.0
    # No interest expense -> DATA_UNAVAILABLE, not "infinitely safe".
    assert calculate_interest_coverage(ebit=100.0, interest_expense=0.0) is None


def test_calculate_return_pct():
    assert calculate_return_pct(start_price=100.0, end_price=120.0) == 20.0
    assert calculate_return_pct(start_price=100.0, end_price=80.0) == -20.0
    assert calculate_return_pct(start_price=0.0, end_price=80.0) is None


def test_calculate_distance_from_high_pct():
    # Peak is 150, latest (last element) is 120 -> (120/150 - 1) * 100 = -20%
    assert calculate_distance_from_high_pct([100.0, 150.0, 130.0, 120.0]) == -20.0
    # Latest price IS the series high -> 0.0, not a negative rounding artifact.
    assert calculate_distance_from_high_pct([100.0, 150.0]) == 0.0
    assert calculate_distance_from_high_pct([]) is None


def test_calculate_annualized_volatility_pct():
    # Alternating +10%/-10% daily returns is high volatility; too few points -> None.
    prices = [100.0, 110.0, 99.0, 108.9, 98.01]
    vol = calculate_annualized_volatility_pct(prices)
    assert vol is not None
    assert vol > 100.0  # roughly 10% daily stdev annualized by sqrt(252) is very large
    assert calculate_annualized_volatility_pct([100.0, 110.0]) is None


def test_calculate_percentile_rank():
    series = [10.0, 15.0, 20.0, 25.0, 30.0]
    # 20.0 is the 3rd of 5 values <= itself -> 60th percentile.
    assert calculate_percentile_rank(20.0, series) == 60.0
    # A value below every peer is the 0th percentile.
    assert calculate_percentile_rank(5.0, series) == 0.0
    # A value at or above every peer is the 100th percentile.
    assert calculate_percentile_rank(100.0, series) == 100.0
    assert calculate_percentile_rank(10.0, []) is None
