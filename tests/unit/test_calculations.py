import pytest

from investment_agent.portfolio.calculations import (
    calculate_cagr,
    calculate_debt_to_equity,
    calculate_max_drawdown,
    calculate_pb_ratio,
    calculate_pe_ratio,
    calculate_portfolio_weights,
    calculate_roce,
    calculate_roe,
    calculate_sector_exposure,
    calculate_sip_future_value,
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
