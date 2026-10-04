"""Deterministic financial calculations implemented in Python.

Financial calculations must never be performed by an LLM;
the LLM interprets the results, while Python computes them accurately.
"""

from collections.abc import Sequence
from typing import Any


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


def calculate_fcf(operating_cash_flow: float, capital_expenditure: float) -> float:
    """Calculate Free Cash Flow = Operating Cash Flow - CapEx.

    `capital_expenditure` should be given as a positive outflow amount. Callers reading it
    from Yahoo's quoteSummary (`capitalExpenditures`) get it back already negative, since
    that is how Yahoo reports it — pass `abs(capitalExpenditures)` in that case.
    """
    return round(operating_cash_flow - capital_expenditure, 2)


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


def calculate_interest_coverage(ebit: float, interest_expense: float) -> float | None:
    """Calculate Interest Coverage Ratio = EBIT / Interest Expense.

    `interest_expense` should be a positive magnitude. Returns None when there is no debt
    to service (interest_expense == 0) rather than raising or dividing by zero — a company
    with no interest expense isn't "infinitely safe", it's DATA_UNAVAILABLE for this ratio.
    """
    if interest_expense == 0:
        return None
    return round(ebit / interest_expense, 2)


def calculate_return_pct(start_price: float, end_price: float) -> float | None:
    """Simple percentage return between two prices. None (not 0) when start_price is 0."""
    if start_price == 0:
        return None
    return round((end_price / start_price - 1.0) * 100.0, 2)


def calculate_distance_from_high_pct(prices: Sequence[float]) -> float | None:
    """How far the latest price sits below the highest price in the series, as a negative
    percentage (0.0 means the latest price *is* the series high). None on empty input."""
    if not prices:
        return None
    peak = max(prices)
    if peak <= 0:
        return None
    latest = prices[-1]
    return round((latest / peak - 1.0) * 100.0, 2)


def calculate_annualized_volatility_pct(prices: Sequence[float], periods_per_year: int = 252) -> float | None:
    """Annualized volatility (% standard deviation) from a series of daily closing prices.

    Uses the population standard deviation of daily simple returns, annualized by
    sqrt(periods_per_year) (252 trading days for equities). None when there are fewer than
    2 return observations (i.e. fewer than 3 prices).
    """
    if len(prices) < 3:
        return None
    returns = [
        (prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices)) if prices[i - 1] != 0
    ]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    daily_vol = variance**0.5
    return round(daily_vol * (periods_per_year**0.5) * 100.0, 2)


def calculate_percentile_rank(value: float, series: Sequence[float]) -> float | None:
    """What percentage of `series` is <= `value` (0-100). None on an empty series.

    Used for "is this P/E cheap or expensive vs. its own history / vs. sector peers" (Gap
    5) — a plain rank, not a statistical distribution assumption, so it degrades sensibly
    for small peer samples instead of asserting false precision.
    """
    if not series:
        return None
    at_or_below = sum(1 for item in series if item <= value)
    return round((at_or_below / len(series)) * 100.0, 2)


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


def _cagr_from_series(entries: list[dict[str, Any]], field: str) -> float | None:
    """CAGR between the oldest and newest entry in a most-recent-first statement list.

    Yahoo's quoteSummary history is ordered newest-first; `entries[0]` is the latest filed
    year and `entries[-1]` is the oldest available (typically 3-4 years back). Returns None
    (DATA_UNAVAILABLE) rather than raising when there's fewer than 2 usable data points or
    either endpoint is non-positive.
    """
    values = [float(value) for entry in entries if (value := entry.get(field)) is not None]
    if len(values) < 2:
        return None
    newest, oldest = values[0], values[-1]
    periods = len(values) - 1
    if oldest <= 0 or newest <= 0 or periods <= 0:
        return None
    return round(calculate_cagr(oldest, newest, periods), 2)


def derive_ratios_from_statements(statements: dict[str, list[dict[str, Any]]]) -> dict[str, float | None]:
    """Gap 2: ROCE, FCF, and revenue/profit CAGR from Yahoo's free annual statements.

    Pure function over `market.yahoo_market.financial_statement_history()`'s output, kept
    separate from any I/O so it's cheaply unit-testable against hand-computed fixtures.
    Every field is None (DATA_UNAVAILABLE) rather than guessed when the source statement is
    missing the figure it needs.
    """
    income = statements.get("income_statements") or []
    balance = statements.get("balance_sheets") or []
    cashflow = statements.get("cash_flows") or []

    roce_pct = None
    if income and balance:
        ebit = income[0].get("ebit")
        total_assets = balance[0].get("total_assets")
        current_liabilities = balance[0].get("total_current_liabilities")
        if ebit is not None and total_assets is not None and current_liabilities is not None:
            capital_employed = total_assets - current_liabilities
            if capital_employed > 0:
                roce_pct = calculate_roce(ebit, capital_employed)

    fcf = None
    if cashflow:
        ocf = cashflow[0].get("operating_cash_flow")
        capex = cashflow[0].get("capex")
        if ocf is not None and capex is not None:
            fcf = calculate_fcf(ocf, abs(capex))

    interest_coverage = None
    if income:
        ebit = income[0].get("ebit")
        interest_expense = income[0].get("interest_expense")
        if ebit is not None and interest_expense is not None:
            interest_coverage = calculate_interest_coverage(ebit, abs(interest_expense))

    return {
        "roce_pct": roce_pct,
        "fcf": fcf,
        "interest_coverage": interest_coverage,
        "revenue_growth_3y_cagr_pct": _cagr_from_series(income, "total_revenue"),
        "profit_growth_3y_cagr_pct": _cagr_from_series(income, "net_income"),
    }


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
