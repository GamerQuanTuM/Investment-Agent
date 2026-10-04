"""Mutual fund metrics: CAGR, SIP backtest + XIRR, drawdown, volatility, rolling returns,
forward projection, LTCG/STCG estimate, and expense-ratio drag. Pure Python, no I/O — every
function here takes already-fetched NAV history (see `market/mfapi.py`) and returns plain
numbers. The LLM never computes any of this; it may only narrate a result already produced
here (per the project-wide hard rule).

Every function returns `None` for a field it cannot responsibly compute (insufficient
history, degenerate cash flows, etc.) rather than a fabricated 0 or guess.
"""

from __future__ import annotations

import calendar
import logging
from bisect import bisect_right
from datetime import date, timedelta
from typing import Any

from investment_agent.portfolio.calculations import calculate_cagr, calculate_sip_future_value

logger = logging.getLogger(__name__)

# Tax config — the single place to update if SEBI/Finance Act rates change. Equity and
# equity-oriented mutual funds only; debt fund gains are taxed at the investor's income
# slab rate, which this module has no way to know, so `ltcg_stcg_estimate` refuses to
# estimate for `is_equity=False` rather than silently using the wrong rate.
LTCG_EXEMPTION_INR = 125_000.0
LTCG_RATE_PCT = 12.5
STCG_RATE_PCT = 20.0
LTCG_HOLDING_YEARS_EQUITY = 1.0


class NavSeries:
    """Chronological (oldest-first) view over mfapi.in's newest-first `nav_history`, with
    nearest-on-or-before lookups for dates that fall on a non-trading day (weekends,
    exchange holidays) — a SIP installment date almost never lands exactly on a NAV date.
    """

    def __init__(self, nav_history: list[dict[str, Any]]):
        chronological = list(reversed(nav_history))
        self.dates = [date.fromisoformat(row["date"]) for row in chronological]
        self.navs = [float(row["nav"]) for row in chronological]

    def __len__(self) -> int:
        return len(self.dates)

    def nav_on_or_before(self, target: date) -> tuple[date, float] | None:
        idx = bisect_right(self.dates, target) - 1
        if idx < 0:
            return None
        return self.dates[idx], self.navs[idx]

    @property
    def latest(self) -> tuple[date, float] | None:
        if not self.dates:
            return None
        return self.dates[-1], self.navs[-1]


def calculate_xirr(cash_flows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Annualized return for irregularly-dated cash flows, via Newton-Raphson.

    `cash_flows` is a list of (date, amount): negative for money paid in, positive for
    money received back. Returns None (never raises) when there are fewer than 2 flows,
    every flow has the same sign (no real return to solve for), or the solver doesn't
    converge within a sane number of iterations.
    """
    if len(cash_flows) < 2:
        return None
    amounts = [amount for _, amount in cash_flows]
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    t0 = cash_flows[0][0]
    years = [(d - t0).days / 365.0 for d, _ in cash_flows]

    def npv(rate: float) -> float:
        return sum(amount / (1.0 + rate) ** t for t, amount in zip(years, amounts, strict=True))

    def npv_derivative(rate: float) -> float:
        return sum(
            -t * amount / (1.0 + rate) ** (t + 1.0) for t, amount in zip(years, amounts, strict=True) if t > 0
        )

    rate = guess
    for _ in range(100):
        value = npv(rate)
        derivative = npv_derivative(rate)
        if derivative == 0:
            return None
        new_rate = rate - value / derivative
        new_rate = max(-0.9999, new_rate)
        if abs(new_rate - rate) < 1e-7:
            return round(new_rate * 100.0, 2)
        rate = new_rate
    logger.info("XIRR solver did not converge within 100 iterations")
    return None


def trailing_cagr(nav_history: list[dict[str, Any]], years: float) -> float | None:
    """CAGR from `years` ago (nearest available NAV on or before that date) to the latest
    NAV. None if the series doesn't go back far enough."""
    series = NavSeries(nav_history)
    latest = series.latest
    if latest is None:
        return None
    latest_date, latest_nav = latest
    target = latest_date - timedelta(days=int(years * 365))
    start = series.nav_on_or_before(target)
    if start is None:
        return None
    start_date, start_nav = start
    actual_years = (latest_date - start_date).days / 365.0
    if actual_years <= 0 or start_nav <= 0 or latest_nav <= 0:
        return None
    return round(calculate_cagr(start_nav, latest_nav, actual_years), 2)


def period_return_pct(nav_history: list[dict[str, Any]], years: float) -> float | None:
    """Simple return from `years` ago to the latest NAV, in percent. None unless the
    series actually covers most of that window, so a new fund is not scored on a few days."""
    series = NavSeries(nav_history)
    latest = series.latest
    if latest is None:
        return None
    latest_date, latest_nav = latest
    target = latest_date - timedelta(days=int(years * 365))
    start = series.nav_on_or_before(target)
    if start is None:
        return None
    start_date, start_nav = start
    covered_days = (latest_date - start_date).days
    if covered_days < int(years * 365 * 0.8) or start_nav <= 0 or latest_nav <= 0:
        return None
    return round((latest_nav / start_nav - 1.0) * 100.0, 2)


def _add_one_month(d: date) -> date:
    month = d.month + 1
    year = d.year
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def sip_backtest(
    nav_history: list[dict[str, Any]],
    monthly_amount: float,
    start_date: date,
    step_up_pct: float = 0.0,
) -> dict[str, Any]:
    """Simulate a monthly SIP from `start_date` to the latest available NAV date on real
    historical NAVs — invested total, units accumulated, current value, and XIRR.

    `step_up_pct` raises the monthly amount by that percentage once a year (every 12
    installments), not every month. Every field is None if there's no usable NAV data at
    or after `start_date`.
    """
    empty = {
        "invested": None,
        "units": None,
        "current_value": None,
        "xirr_pct": None,
        "start_date": None,
        "end_date": None,
    }
    series = NavSeries(nav_history)
    latest = series.latest
    if latest is None or start_date > latest[0]:
        return empty
    latest_date, latest_nav = latest

    cash_flows: list[tuple[date, float]] = []
    total_units = 0.0
    total_invested = 0.0
    current_amount = monthly_amount
    cursor = start_date
    installment_index = 0
    while cursor <= latest_date:
        found = series.nav_on_or_before(cursor)
        if found is not None:
            found_date, nav_value = found
            if nav_value > 0:
                if installment_index > 0 and installment_index % 12 == 0 and step_up_pct:
                    current_amount = round(current_amount * (1 + step_up_pct / 100.0), 2)
                units = current_amount / nav_value
                total_units += units
                total_invested += current_amount
                cash_flows.append((found_date, -current_amount))
                installment_index += 1
        cursor = _add_one_month(cursor)

    if total_units <= 0 or not cash_flows:
        return empty

    current_value = round(total_units * latest_nav, 2)
    cash_flows.append((latest_date, current_value))

    return {
        "invested": round(total_invested, 2),
        "units": round(total_units, 4),
        "current_value": current_value,
        "xirr_pct": calculate_xirr(cash_flows),
        "start_date": cash_flows[0][0].isoformat(),
        "end_date": latest_date.isoformat(),
    }


def rolling_return_extremes(nav_history: list[dict[str, Any]], window_years: float = 3.0) -> dict[str, float | None]:
    """Best and worst `window_years`-CAGR starting from any point in the history.

    Steps through candidate start dates roughly monthly (not every trading day) — this is
    a screening metric meant to show "how different can your outcome be depending on when
    you entered," not a precise day-by-day backtest. None for either value if the series
    doesn't span a full `window_years` window at all.
    """
    series = NavSeries(nav_history)
    if len(series) < 2:
        return {"best_pct": None, "worst_pct": None}
    window_days = int(window_years * 365)
    best: float | None = None
    worst: float | None = None
    step = 21  # ~1 trading month

    for i in range(0, len(series) - 1, step):
        start_date, start_nav = series.dates[i], series.navs[i]
        if start_nav <= 0:
            continue
        end = series.nav_on_or_before(start_date + timedelta(days=window_days))
        if end is None:
            continue
        end_date, end_nav = end
        actual_years = (end_date - start_date).days / 365.0
        if actual_years < window_years * 0.9 or end_nav <= 0:
            continue
        cagr = calculate_cagr(start_nav, end_nav, actual_years)
        best = cagr if best is None else max(best, cagr)
        worst = cagr if worst is None else min(worst, cagr)

    return {
        "best_pct": round(best, 2) if best is not None else None,
        "worst_pct": round(worst, 2) if worst is not None else None,
    }


def project_sip(
    monthly_amount: float,
    years: int,
    annual_return_pct: float,
    step_up_pct: float = 0.0,
    inflation_pct: float = 0.0,
) -> dict[str, float]:
    """Forward-looking SIP projection — nominal and inflation-adjusted corpus.

    This is explicitly an *assumption*, not a forecast (callers/UI must label it as such):
    the real future return is unknown, so this just compounds a chosen flat rate.
    `step_up_pct` grows the monthly contribution once a year.
    """
    if monthly_amount <= 0 or years <= 0:
        return {"invested": 0.0, "nominal_corpus": 0.0, "inflation_adjusted_corpus": 0.0}

    if step_up_pct <= 0:
        nominal = calculate_sip_future_value(monthly_amount, annual_return_pct, years)
        invested = monthly_amount * years * 12
    else:
        nominal = 0.0
        invested = 0.0
        current_amount = monthly_amount
        for year_index in range(years):
            year_end_value = calculate_sip_future_value(current_amount, annual_return_pct, 1)
            remaining_years = years - year_index - 1
            nominal += year_end_value * ((1 + annual_return_pct / 100.0) ** remaining_years)
            invested += current_amount * 12
            current_amount = round(current_amount * (1 + step_up_pct / 100.0), 2)

    inflation_adjusted = (
        round(nominal / ((1 + inflation_pct / 100.0) ** years), 2) if inflation_pct > 0 else round(nominal, 2)
    )
    return {
        "invested": round(invested, 2),
        "nominal_corpus": round(nominal, 2),
        "inflation_adjusted_corpus": inflation_adjusted,
    }


def ltcg_stcg_estimate(gains: float, holding_period_years: float, is_equity: bool = True) -> dict[str, Any]:
    """LTCG/STCG estimate for an **equity-oriented** fund redemption.

    Deliberately refuses to estimate for `is_equity=False`: debt fund gains are taxed at
    the investor's income slab rate, which this function has no way to know, and guessing
    one would violate the no-fabricated-numbers rule.
    """
    if not is_equity:
        return {
            "tax": None,
            "tax_type": "DATA_UNAVAILABLE",
            "rate_pct": None,
            "note": "Debt fund gains are taxed at your income slab rate; not estimated here.",
        }
    if gains <= 0:
        return {"tax": 0.0, "tax_type": "NONE", "rate_pct": 0.0, "note": "No gain, no tax."}

    if holding_period_years >= LTCG_HOLDING_YEARS_EQUITY:
        exemption_used = min(gains, LTCG_EXEMPTION_INR)
        taxable = max(0.0, gains - LTCG_EXEMPTION_INR)
        return {
            "tax": round(taxable * LTCG_RATE_PCT / 100.0, 2),
            "tax_type": "LTCG",
            "rate_pct": LTCG_RATE_PCT,
            "exemption_used": round(exemption_used, 2),
        }
    return {
        "tax": round(gains * STCG_RATE_PCT / 100.0, 2),
        "tax_type": "STCG",
        "rate_pct": STCG_RATE_PCT,
        "exemption_used": 0.0,
    }


def expense_ratio_drag(
    monthly_amount: float,
    years: int,
    annual_return_pct: float,
    ter_regular_pct: float,
    ter_direct_pct: float,
) -> dict[str, float]:
    """Illustrative cost of a Regular vs. Direct plan's expense ratio over an SIP horizon.

    Modeled the standard way: a fund's expense ratio is a direct drag on the net return an
    investor receives, so each plan's corpus is projected at `annual_return_pct` minus that
    plan's TER.
    """
    corpus_regular = calculate_sip_future_value(monthly_amount, max(annual_return_pct - ter_regular_pct, 0.0), years)
    corpus_direct = calculate_sip_future_value(monthly_amount, max(annual_return_pct - ter_direct_pct, 0.0), years)
    return {
        "corpus_regular": corpus_regular,
        "corpus_direct": corpus_direct,
        "savings_from_direct": round(corpus_direct - corpus_regular, 2),
    }
