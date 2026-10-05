"""Hallucination guard: model text may only repeat tickers and numbers from the result."""

from __future__ import annotations

import pytest

from investment_agent.research.llm_guard import allowed_numbers, is_grounded

STRUCTURED = {
    "budget": 10000.0,
    "total_invested": 9650.4,
    "rows": [
        {"symbol": "TCS", "shares": 2, "amount_inr": 7000.0, "weight_pct": 72.5},
        {"symbol": "INFY", "shares": 3, "amount_inr": 2650.4, "weight_pct": 27.5},
    ],
    "data_as_of": "2026-10-05",
}
TICKERS = ["TCS", "INFY"]


@pytest.mark.parametrize(
    "text",
    [
        "Here are 2 stocks for your ₹10,000: TCS and INFY, with about ₹9,650 invested.",
        "TCS is 72.5% and INFY is 27.5% of what you invest, as of 2026-10-05.",
        "Two sectors, nothing here is a forecast.",
    ],
)
def test_grounded_text_passes(text):
    assert is_grounded(text, STRUCTURED, TICKERS)


@pytest.mark.parametrize(
    "text",
    [
        "TCS and WIPRO look good.",  # ticker not in the result
        "TCS at ₹4,321 is cheap.",  # price not in the result
        "INFY returned 18.4% last year.",  # figure not in the result
        "TCS will rise next year.",  # forecast language
        "Your target price for TCS is a sure-shot winner.",
        "Expected return is high on INFY.",
        "",
    ],
)
def test_ungrounded_text_is_rejected(text):
    assert not is_grounded(text, STRUCTURED, TICKERS)


def test_rounded_figures_are_allowed_but_not_arbitrary_ones():
    assert is_grounded("About ₹9,650 is invested.", STRUCTURED, TICKERS)
    assert not is_grounded("About ₹9,700 is invested.", STRUCTURED, TICKERS)


def test_allowed_numbers_includes_dates_and_list_sizes():
    numbers = allowed_numbers(STRUCTURED)
    assert {2026.0, 10.0, 5.0, 2.0, 9650.0} <= numbers
