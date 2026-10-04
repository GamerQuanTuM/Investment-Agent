"""Orchestrates the F2 deterministic score for one stock: live quote, 5y price history,
fundamentals + statements (Yahoo), NSE shareholding (promoter pledge), and sector peers
from our own screened universe (DB) for the Gap-5 valuation percentile.

Python (portfolio/calculations.py, portfolio/scoring.py) computes every number here. The
optional LLM call at the end may only narrate the finished card in plain language — it
never sees raw statements and cannot change a score, only describe one already computed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.market.nse import get_shareholding, latest_promoter_pledge_pct
from investment_agent.market.universe import load_candidates_from_db
from investment_agent.market.yahoo_market import (
    chart_symbol,
    company_fundamentals,
    financial_statement_history,
    quote_symbol,
)
from investment_agent.portfolio.calculations import (
    calculate_annualized_volatility_pct,
    calculate_distance_from_high_pct,
    calculate_max_drawdown,
    calculate_pb_ratio,
    calculate_return_pct,
    derive_ratios_from_statements,
)
from investment_agent.portfolio.scoring import build_score_card

logger = logging.getLogger(__name__)

VALUATION_NOTE = (
    "P/E vs. own history uses 5 years of daily prices against today's EPS (historical EPS "
    "isn't available from a free source), so it approximates 'is this price cheap relative "
    "to its own range', not a true historical P/E series."
)


def _closes_from_candles(candles: list[dict[str, Any]]) -> list[float]:
    return [float(candle["close"]) for candle in candles if candle.get("close") is not None]


async def _sector_peer_pe_values(sector: str | None, exclude_symbol: str) -> list[float]:
    """Current P/E of other screened candidates sharing this stock's sector (Gap 5)."""
    if not sector:
        return []
    try:
        candidates = await load_candidates_from_db()
    except Exception as exc:
        logger.info("Sector peer lookup unavailable: %s", exc)
        return []
    return [
        candidate["pe_ratio"]
        for candidate in candidates
        if candidate.get("sector") == sector
        and candidate.get("symbol") != exclude_symbol.upper()
        and candidate.get("pe_ratio")
    ]


def _fallback_explanation(symbol: str, card: dict[str, Any]) -> str:
    overall = card.get("overall")
    if overall is None:
        return f"Not enough data was available to score {symbol} responsibly right now."
    if overall >= 70:
        verdict = "scores well across the factors we could measure"
    elif overall >= 40:
        verdict = "is mixed — some factors look fine, others don't"
    else:
        verdict = "scores poorly on the factors we could measure"
    return f"{symbol} {verdict} (overall {overall}/100)."


async def _explain(symbol: str, card: dict[str, Any]) -> str:
    """LLM narrates the finished numbers only; a deterministic fallback covers any failure."""
    try:
        model = get_llm("cheap")
        prompt = (
            "Explain this investment score card in 2-3 plain sentences for someone with "
            "basic investing knowledge. Use ONLY the numbers given — do not invent or adjust "
            f"any figure. Card: {json.dumps(card)}"
        )
        reply = await model.ainvoke(prompt)
        text = extract_text(reply.content)
        text = text.strip()
        return text or _fallback_explanation(symbol, card)
    except Exception as exc:
        logger.info("Score explanation model unavailable for %s: %s", symbol, exc)
        return _fallback_explanation(symbol, card)


async def build_stock_score(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    symbol = symbol.upper()
    quote = await quote_symbol(symbol, exchange)
    if quote is None:
        return {
            "symbol": symbol,
            "status": "DATA_UNAVAILABLE",
            "message": "No live quote is available, so this stock cannot be scored.",
        }

    try:
        chart_5y = await chart_symbol(symbol, "5y", exchange)
    except Exception:
        chart_5y = None
    closes_5y = _closes_from_candles((chart_5y or {}).get("candles") or [])
    closes_1y = closes_5y[-252:] if len(closes_5y) >= 252 else closes_5y

    try:
        fundamentals = await company_fundamentals(symbol, exchange)
    except Exception:
        fundamentals = {}
    try:
        statements = await financial_statement_history(symbol, exchange)
    except Exception:
        statements = {"income_statements": [], "balance_sheets": [], "cash_flows": []}
    ratios = derive_ratios_from_statements(statements)

    try:
        shareholding = await get_shareholding(symbol)
        pledge_pct = latest_promoter_pledge_pct(shareholding)
    except Exception:
        pledge_pct = None

    pe_ratio = quote.get("pe_ratio") or fundamentals.get("pe_ratio")
    book_value = fundamentals.get("book_value")
    pb_ratio = None
    live_price = quote.get("live_price")
    if book_value and live_price:
        try:
            pb_ratio = calculate_pb_ratio(live_price, book_value)
        except ValueError:
            pb_ratio = None

    eps = fundamentals.get("eps")
    pe_history = [round(close / eps, 2) for close in closes_5y if eps] if eps and eps > 0 else []
    sector_pe_values = await _sector_peer_pe_values(fundamentals.get("sector"), symbol)

    return_6m = calculate_return_pct(closes_1y[-126], closes_1y[-1]) if len(closes_1y) >= 126 else None
    return_12m = calculate_return_pct(closes_1y[0], closes_1y[-1]) if len(closes_1y) >= 2 else None
    distance_52w = calculate_distance_from_high_pct(closes_1y) if closes_1y else None
    volatility = calculate_annualized_volatility_pct(closes_1y) if closes_1y else None
    max_dd = calculate_max_drawdown(closes_1y) if closes_1y else None

    card = build_score_card(
        quality_inputs={
            "roe_pct": fundamentals.get("roe_pct"),
            "roce_pct": ratios.get("roce_pct"),
            "debt_to_equity": fundamentals.get("debt_to_equity"),
            "interest_coverage": ratios.get("interest_coverage"),
            "fcf": ratios.get("fcf"),
            "revenue_growth_3y_cagr_pct": ratios.get("revenue_growth_3y_cagr_pct"),
            "profit_growth_3y_cagr_pct": ratios.get("profit_growth_3y_cagr_pct"),
        },
        valuation_inputs={
            "pe_ratio": pe_ratio,
            "pe_history": pe_history,
            "pb_ratio": pb_ratio,
            "sector_pe_values": sector_pe_values,
        },
        momentum_inputs={
            "return_6m_pct": return_6m,
            "return_12m_pct": return_12m,
            "distance_from_52w_high_pct": distance_52w,
        },
        risk_inputs={
            "annualized_volatility_pct": volatility,
            "max_drawdown_pct": max_dd,
            "promoter_pledge_pct": pledge_pct,
        },
    )

    explanation = await _explain(symbol, card)

    return {
        "symbol": symbol,
        "name": quote.get("name", symbol),
        "status": "OK",
        **card,
        "explanation": explanation,
        "valuation_note": VALUATION_NOTE,
        "data_as_of": quote.get("as_of"),
    }
