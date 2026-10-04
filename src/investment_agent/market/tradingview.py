"""Extra ratios from the TradingView screener, alongside the Yahoo quote."""

from __future__ import annotations

import math
from typing import Any

from tvscreener import Market, StockField, StockScreener


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return round(number, 2)


def merge_fundamentals(primary: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Fill gaps from TradingView. Keep Yahoo earnings and book value when present."""
    merged = dict(primary)
    for key, value in extra.items():
        if value is None:
            continue
        if key in {"eps", "book_value"} and merged.get(key) is not None:
            continue
        if merged.get(key) is None:
            merged[key] = value
    sources = [item for item in (primary.get("source"), extra.get("source")) if item]
    if sources:
        merged["source"] = " + ".join(dict.fromkeys(sources))
    return merged


def tradingview_fundamentals(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    prefix = "BSE" if exchange.upper() == "BSE" else "NSE"
    ticker = f"{prefix}:{symbol.upper().removesuffix('.NS').removesuffix('.BO')}"
    fields = {
        StockField.PRICE_TO_EARNINGS_RATIO_TTM: "pe_ratio",
        StockField.RETURN_ON_EQUITY_TTM: "roe_pct",
        StockField.RETURN_ON_INVESTED_CAPITAL_TTM: "roic_pct",
        StockField.DEBT_TO_EQUITY_RATIO_MRQ: "debt_to_equity",
        StockField.REVENUE_ANNUAL_YOY_GROWTH: "revenue_growth_pct",
        StockField.NET_INCOME_ANNUAL_YOY_GROWTH: "earnings_growth_pct",
        StockField.OPERATING_MARGIN_TTM: "operating_margin_pct",
        StockField.NET_MARGIN_TTM: "profit_margin_pct",
        StockField.PRICE_TO_BOOK_MRQ: "price_to_book",
        StockField.DIVIDEND_YIELD_FORWARD: "dividend_yield_pct",
        StockField.RECOMMENDATION_MARK: "analyst_score",
    }
    screener = StockScreener()
    screener.set_markets(Market.INDIA)
    screener.symbols = {"tickers": [ticker], "query": {"types": []}}
    screener.select(*fields.keys())
    frame = screener.get()
    if frame is None or frame.empty:
        return {}
    row = frame.iloc[0]
    payload: dict[str, Any] = {"source": "TradingView screener"}
    for field, key in fields.items():
        label = getattr(field, "label", None) or field.name
        payload[key] = _number(row.get(label))
    return payload
