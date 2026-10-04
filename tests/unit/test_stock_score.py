"""Wiring test for research/stock_score.py — every I/O dependency is monkeypatched, so this
verifies build_stock_score assembles portfolio/scoring.py's inputs correctly (right kwargs,
right field names) rather than re-testing the scoring math itself (see test_scoring.py)."""

from __future__ import annotations

import pytest

from investment_agent.research import stock_score


@pytest.fixture(autouse=True)
def _stub_dependencies(monkeypatch: pytest.MonkeyPatch):
    async def fake_quote_symbol(symbol: str, exchange: str):
        return {
            "symbol": symbol,
            "name": "Fake Co",
            "live_price": 100.0,
            "pe_ratio": 20.0,
            "as_of": "2026-10-04T00:00:00+00:00",
        }

    async def fake_chart_symbol(symbol: str, range_key: str, exchange: str):
        # 260 flat-then-rising daily closes so 6m/12m return and volatility are computable.
        closes = [80.0] * 130 + [90.0] * 126 + [100.0] * 4
        return {"candles": [{"close": c} for c in closes]}

    async def fake_company_fundamentals(symbol: str, exchange: str):
        return {
            "sector": "Technology",
            "roe_pct": 20.0,
            "debt_to_equity": 0.5,
            "eps": 5.0,
            "book_value": 50.0,
        }

    async def fake_financial_statement_history(symbol: str, exchange: str):
        return {
            "income_statements": [
                {"total_revenue": 200.0, "ebit": 50.0, "net_income": 36.0, "interest_expense": -10.0},
                {"total_revenue": 100.0, "ebit": 20.0, "net_income": 18.0},
            ],
            "balance_sheets": [{"total_assets": 600.0, "total_current_liabilities": 100.0}],
            "cash_flows": [{"operating_cash_flow": 80.0, "capex": -20.0}],
        }

    async def fake_get_shareholding(symbol: str):
        return [{"promoter_pledge_pct": 0.0}]

    async def fake_load_candidates_from_db():
        return [
            {"symbol": "PEER1", "sector": "Technology", "pe_ratio": 25.0},
            {"symbol": "PEER2", "sector": "Technology", "pe_ratio": 30.0},
        ]

    async def fake_explain(symbol: str, card: dict) -> str:
        return "stubbed explanation"

    monkeypatch.setattr(stock_score, "quote_symbol", fake_quote_symbol)
    monkeypatch.setattr(stock_score, "chart_symbol", fake_chart_symbol)
    monkeypatch.setattr(stock_score, "company_fundamentals", fake_company_fundamentals)
    monkeypatch.setattr(stock_score, "financial_statement_history", fake_financial_statement_history)
    monkeypatch.setattr(stock_score, "get_shareholding", fake_get_shareholding)
    monkeypatch.setattr(stock_score, "load_candidates_from_db", fake_load_candidates_from_db)
    monkeypatch.setattr(stock_score, "_explain", fake_explain)


async def test_build_stock_score_assembles_full_card():
    result = await stock_score.build_stock_score("TCS", "NSE")

    assert result["status"] == "OK"
    assert result["symbol"] == "TCS"
    assert set(result.keys()) >= {"quality", "valuation", "momentum", "risk", "overall", "explanation"}
    assert result["explanation"] == "stubbed explanation"

    # Quality block should have picked up ROE/debt from fundamentals and ROCE/FCF/interest
    # coverage from the derived statement ratios.
    quality_inputs = {item["label"]: item["value"] for item in result["quality"]["inputs"]}
    assert quality_inputs["Return on equity"] == 20.0
    assert quality_inputs["Debt to equity"] == 0.5
    assert quality_inputs["Return on capital employed"] == 10.0  # 50 / (600-100) * 100
    assert quality_inputs["Interest coverage"] == 5.0  # 50 / 10

    # Valuation should have used the sector peers we stubbed in.
    valuation_inputs = {item["label"]: item["value"] for item in result["valuation"]["inputs"]}
    assert valuation_inputs["Current P/E"] == 20.0
    assert valuation_inputs["P/E vs. sector peers"] is not None

    # Momentum should be non-trivially positive given the rising price series.
    assert result["momentum"]["score"] is not None
    assert result["momentum"]["score"] > 50.0

    # Risk should reflect zero promoter pledge.
    risk_inputs = {item["label"]: item["value"] for item in result["risk"]["inputs"]}
    assert risk_inputs["Promoter pledge"] == 0.0

    assert result["overall"] is not None
    assert 0.0 <= result["overall"] <= 100.0


async def test_build_stock_score_degrades_when_quote_missing(monkeypatch: pytest.MonkeyPatch):
    async def fake_quote_symbol_none(symbol: str, exchange: str):
        return None

    monkeypatch.setattr(stock_score, "quote_symbol", fake_quote_symbol_none)

    result = await stock_score.build_stock_score("NOSUCH", "NSE")

    assert result["status"] == "DATA_UNAVAILABLE"
    assert "quality" not in result
