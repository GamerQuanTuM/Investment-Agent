from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from investment_agent.config.settings import get_settings
from investment_agent.market.board import (
    history_for_symbol,
    live_indices,
    quote_for_symbol,
    trending_board,
)
from investment_agent.market.fundamentals import store_fundamental_snapshots
from investment_agent.market.indstocks import IndstocksError
from investment_agent.market.sync import refresh_market_data
from investment_agent.market.universe import load_portfolio_from_broker

router = APIRouter(prefix="/market", tags=["Market"])


class FundamentalIn(BaseModel):
    symbol: str
    name: str = ""
    sector: str = "Unclassified"
    security_id: str | None = None
    asset_type: str = "stock"
    data_date: datetime
    roe_pct: float | None = None
    roce_pct: float | None = None
    debt_to_equity: float | None = None
    promoter_pledge_pct: float | None = None
    revenue_growth_3y_cagr_pct: float | None = None
    profit_growth_3y_cagr_pct: float | None = None
    eps: float | None = None
    book_value_per_share: float | None = None
    market_cap_cr: float | None = None
    source_name: str
    source_url: str
    source_type: str = "Company Filing"


class FundamentalBatch(BaseModel):
    snapshots: list[FundamentalIn] = Field(min_length=1)


@router.get("/trending")
async def trending(offset: int = 0, limit: int = 20, exchange: str = "NSE") -> dict[str, Any]:
    """NSE or BSE equities ranked by session move."""
    try:
        return await trending_board(offset=offset, limit=limit, exchange=exchange)
    except IndstocksError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/search")
async def search(q: str, exchange: str = "NSE") -> dict[str, Any]:
    from investment_agent.market.yahoo_market import MarketDataError, search_symbols

    try:
        return {"items": await search_symbols(q, exchange)}
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/indices")
async def indices() -> dict[str, Any]:
    try:
        return {"items": await live_indices()}
    except IndstocksError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/stocks/{symbol}")
async def stock_quote(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    try:
        quote = await quote_for_symbol(symbol, exchange)
    except IndstocksError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if quote is None:
        raise HTTPException(status_code=404, detail=f"No live quote for {symbol.upper()}")
    return quote


@router.get("/stocks/{symbol}/history")
async def stock_history(symbol: str, range: str = "1y", exchange: str = "NSE") -> dict[str, Any]:
    try:
        history = await history_for_symbol(symbol, range.lower(), exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IndstocksError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if history is None:
        raise HTTPException(status_code=404, detail=f"No history for {symbol.upper()}")
    return history


@router.get("/stocks/{symbol}/filings")
async def stock_filings(symbol: str) -> dict[str, Any]:
    """Latest corporate announcements from NSE. Empty list, not an error, when unavailable."""
    from investment_agent.market.nse import get_filings

    filings = await get_filings(symbol)
    return {
        "symbol": symbol.upper(),
        "status": "OK" if filings else "DATA_UNAVAILABLE",
        "filings": filings,
    }


@router.get("/stocks/{symbol}/shareholding")
async def stock_shareholding(symbol: str) -> dict[str, Any]:
    """Quarter-wise promoter/FII/DII/public holding and promoter pledge from NSE."""
    from investment_agent.market.nse import get_shareholding

    quarters = await get_shareholding(symbol)
    return {
        "symbol": symbol.upper(),
        "status": "OK" if quarters else "DATA_UNAVAILABLE",
        "quarters": quarters,
    }


@router.get("/stocks/{symbol}/news")
async def stock_news(symbol: str, name: str | None = None) -> dict[str, Any]:
    """Recent news headlines (Google News RSS) plus a deterministic lexicon-based
    sentiment score (F4) — not an LLM/ML sentiment model. `name` (the company name) gives
    a far more relevant search than the bare ticker symbol; falls back to the symbol
    alone when omitted."""
    from investment_agent.market.news import get_news
    from investment_agent.research.sentiment import aggregate_sentiment

    query = f"{name or symbol} stock NSE"
    articles = await get_news(query)
    sentiment = aggregate_sentiment(articles)
    return {
        "symbol": symbol.upper(),
        "status": "OK" if articles else "DATA_UNAVAILABLE",
        "articles": articles,
        "sentiment": sentiment,
    }


@router.get("/macro")
async def macro_snapshot() -> dict[str, Any]:
    """USD/INR spot rate and YoY CPI inflation (F3), from FRED's free CSV export. Each
    field degrades to its own `DATA_UNAVAILABLE` rather than failing the whole response —
    see `market/macro.py` for why RBI's own discount-rate series was deliberately left
    out (too stale to show as current)."""
    from investment_agent.market.macro import get_macro_snapshot

    return await get_macro_snapshot()


@router.get("/portfolio")
async def portfolio() -> dict[str, Any]:
    """Live Demat holdings and cash. Empty when the broker session is not configured."""
    settings = get_settings()
    if not settings.indstocks_configured:
        return {
            "broker_name": "INDmoney (INDstocks)",
            "auth_status": "DISCONNECTED",
            "cash_available": None,
            "portfolio_total_value": None,
            "day_change_pnl": None,
            "day_change_pct": None,
            "holdings": [],
        }
    try:
        book = await load_portfolio_from_broker()
    except Exception:
        return {
            "broker_name": "INDmoney (INDstocks)",
            "auth_status": "DISCONNECTED",
            "cash_available": None,
            "portfolio_total_value": None,
            "day_change_pnl": None,
            "day_change_pct": None,
            "holdings": [],
        }
    if book is None:
        return {
            "broker_name": "INDmoney (INDstocks)",
            "auth_status": "DISCONNECTED",
            "cash_available": None,
            "portfolio_total_value": None,
            "day_change_pnl": None,
            "day_change_pct": None,
            "holdings": [],
        }
    holdings = []
    invested = 0.0
    market = 0.0
    for row in book.get("holdings", []):
        qty = float(row.get("quantity") or 0)
        avg = float(row.get("average_buy_price") or 0)
        ltp = row.get("current_price")
        value = float(row.get("market_value") or 0)
        cost = qty * avg
        pnl = value - cost if ltp is not None else None
        pnl_pct = (pnl / cost * 100.0) if pnl is not None and cost else None
        invested += cost
        market += value
        holdings.append(
            {
                "symbol": row.get("symbol"),
                "company_name": row.get("symbol"),
                "quantity": qty,
                "avg_buy_price": avg,
                "current_ltp": ltp,
                "current_value": value,
                "invested_value": cost,
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
                "sector": row.get("sector") or "Equity",
                "allocation_pct": 0.0,
            }
        )
    for row in holdings:
        if market > 0 and row["current_value"]:
            row["allocation_pct"] = round(row["current_value"] / market * 100.0, 2)
    return {
        "broker_name": "INDmoney (INDstocks)",
        "auth_status": "CONNECTED",
        "cash_available": book.get("cash_available"),
        "portfolio_total_value": book.get("total_value"),
        "day_change_pnl": round(market - invested, 2) if holdings else None,
        "day_change_pct": round((market - invested) / invested * 100.0, 2) if invested else None,
        "holdings": holdings,
    }


@router.get("/portfolio/concentration")
async def portfolio_concentration() -> dict[str, Any]:
    """Sector exposure and single-holding concentration (Gap 8), computed over the same
    live holdings `GET /market/portfolio` returns."""
    from investment_agent.research.portfolio_insights import build_concentration_report

    book = await portfolio()
    return build_concentration_report(book["holdings"])


@router.get("/portfolio/alerts")
async def portfolio_alerts() -> dict[str, Any]:
    """Deterministic, threshold-based portfolio alerts (F8) — drawdown and concentration
    flags only, no day-trading signal, no LLM call."""
    from investment_agent.research.alerts import generate_portfolio_alerts

    book = await portfolio()
    return {"alerts": generate_portfolio_alerts(book["holdings"])}


@router.get("/status")
async def market_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "indstocks_configured": settings.indstocks_configured,
        "watchlist": settings.indstocks_watchlist,
        "amfi_scheme_codes": settings.amfi_scheme_codes,
        "fundamentals": "Submit sourced snapshots to POST /market/fundamentals. INDstocks does not provide ratios.",
    }


@router.post("/refresh")
async def refresh_market() -> dict[str, Any]:
    """Download INDstocks instruments, daily bars, quotes, holdings, and configured AMFI NAVs."""
    try:
        return await refresh_market_data()
    except IndstocksError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Market refresh failed: {exc}") from exc


@router.post("/fundamentals")
async def ingest_fundamentals(batch: FundamentalBatch) -> dict[str, Any]:
    """Store company ratios that already name a source. P/E is computed later from price and EPS."""
    try:
        count = await store_fundamental_snapshots(
            [row.model_dump(mode="json") for row in batch.snapshots]
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not store fundamentals: {exc}") from exc
    return {"stored": count}
