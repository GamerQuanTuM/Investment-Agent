"""Deterministic financial calculations implemented in Python.

Financial calculations must never be performed by an LLM;
the LLM interprets the results, while Python computes them accurately.
"""

from collections.abc import Sequence


def calculate_cagr(start_value: float, end_value: float, periods_in_years: float) -> float:
    """Calculate Compound Annual Growth Rate (CAGR) in percentage.

    CAGR = ((end_value / start_value) ** (1 / periods_in_years) - 1) * 100
    """
    if start_value <= 0 or end_value <= 0 or periods_in_years <= 0:
        raise ValueError("Values and periods must be strictly positive to calculate CAGR")
    return ((end_value / start_value) ** (1.0 / periods_in_years) - 1.0) * 100.0


def calculate_pe_ratio(current_price: float, eps: float) -> float:
    """Calculate Price-to-Earnings (P/E) ratio."""
    if eps <= 0:
        raise ValueError("EPS must be positive to calculate standard P/E ratio")
    return round(current_price / eps, 2)


def calculate_pb_ratio(current_price: float, book_value_per_share: float) -> float:
    """Calculate Price-to-Book (P/B) ratio."""
    if book_value_per_share <= 0:
        raise ValueError("Book value per share must be positive to calculate P/B ratio")
    return round(current_price / book_value_per_share, 2)


def calculate_debt_to_equity(total_debt: float, total_equity: float) -> float:
    """Calculate Debt-to-Equity ratio."""
    if total_equity <= 0:
        raise ValueError("Total equity must be positive to calculate Debt-to-Equity ratio")
    return round(total_debt / total_equity, 2)


def calculate_roe(net_income: float, shareholder_equity: float) -> float:
    """Calculate Return on Equity (ROE) as a percentage."""
    if shareholder_equity <= 0:
        raise ValueError("Shareholder equity must be positive to calculate ROE")
    return round((net_income / shareholder_equity) * 100.0, 2)


def calculate_roce(ebit: float, capital_employed: float) -> float:
    """Calculate Return on Capital Employed (ROCE) as a percentage.

    Capital Employed = Total Assets - Current Liabilities (or Equity + Total Debt).
    """
    if capital_employed <= 0:
        raise ValueError("Capital employed must be positive to calculate ROCE")
    return round((ebit / capital_employed) * 100.0, 2)


def calculate_portfolio_weights(holding_values: dict[str, float]) -> dict[str, float]:
    """Calculate allocation percentage for each holding relative to total portfolio value."""
    total_val = sum(holding_values.values())
    if total_val <= 0:
        return {k: 0.0 for k in holding_values}
    return {k: round((v / total_val) * 100.0, 2) for k, v in holding_values.items()}


def calculate_sector_exposure(
    holdings: Sequence[dict[str, float | str]],
) -> dict[str, float]:
    """Calculate sector concentration percentages.

    Each holding item must contain 'sector' (str) and 'market_value' (float).
    """
    sector_totals: dict[str, float] = {}
    total_val = 0.0

    for h in holdings:
        sector = str(h.get("sector", "Unclassified"))
        val = float(h.get("market_value", 0.0))
        sector_totals[sector] = sector_totals.get(sector, 0.0) + val
        total_val += val

    if total_val <= 0:
        return {s: 0.0 for s in sector_totals}

    return {s: round((val / total_val) * 100.0, 2) for s, val in sector_totals.items()}


def calculate_max_drawdown(prices: Sequence[float]) -> float:
    """Calculate maximum peak-to-trough drawdown percentage.

    Returns a negative percentage or 0.0.
    """
    if not prices or len(prices) < 2:
        return 0.0

    peak = prices[0]
    max_dd = 0.0

    for price in prices:
        peak = max(peak, price)
        dd = ((price - peak) / peak) * 100.0
        max_dd = min(max_dd, dd)

    return round(max_dd, 2)


def calculate_sip_future_value(
    monthly_investment: float,
    annual_rate_pct: float,
    years: int,
) -> float:
    """Calculate future value of a monthly Systematic Investment Plan (SIP).

    Formula: FV = P * [((1 + i)**n - 1) / i] * (1 + i)
    where:
        P = monthly amount
        i = monthly interest rate (annual_rate_pct / 12 / 100)
        n = total months (years * 12)
    """
    if monthly_investment <= 0 or years <= 0:
        return 0.0

    n = years * 12
    if annual_rate_pct == 0:
        return round(monthly_investment * n, 2)

    i = (annual_rate_pct / 100.0) / 12.0
    fv = monthly_investment * (((1.0 + i) ** n - 1.0) / i) * (1.0 + i)
    return round(fv, 2)
