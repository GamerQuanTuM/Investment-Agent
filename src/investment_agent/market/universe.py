"""Build research candidates and portfolio snapshots from stored market data."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from investment_agent.config.settings import get_settings
from investment_agent.db.models.market import DailyBar, FundamentalSnapshot, Instrument
from investment_agent.db.models.user import InvestmentProfile, User
from investment_agent.db.session import async_session_factory
from investment_agent.market.indstocks import IndstocksClient, equity_cash_available, scrip_code
from investment_agent.portfolio.calculations import calculate_pe_ratio

logger = logging.getLogger(__name__)

INDSTOCKS_PRICE_URL = "https://api.indstocks.com/market/historical/1day"


async def load_user_profile_from_db(user_id: str) -> dict[str, Any] | None:
    try:
        async with async_session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            if user is None:
                return None
            profile = await session.scalar(
                select(InvestmentProfile).where(InvestmentProfile.user_id == user_id)
            )
            if profile is None:
                return None
            return {
                "user_id": user_id,
                "risk_tolerance": profile.risk_tolerance,
                "investment_horizon_years": profile.investment_horizon_years,
                "monthly_budget": profile.monthly_budget,
                "max_single_stock_allocation_pct": profile.max_single_stock_allocation_pct,
                "max_sector_allocation_pct": profile.max_sector_allocation_pct,
                "financial_goal": profile.financial_goal,
                "profile_source": "database",
            }
    except Exception:
        logger.info("User profile database lookup unavailable for %s", user_id)
        return None


_MASTER_TTL = timedelta(minutes=10)
_master_cache: tuple[datetime, list[dict[str, str]]] | None = None


async def load_symbol_master() -> list[dict[str, str]]:
    """Every NSE equity symbol we hold (instrument master plus fundamentals), with the
    company name when a fundamental snapshot carries one. This is the only place chat may
    accept a ticker from. Empty when the DB is unreachable or the sync has not run."""
    global _master_cache
    now = datetime.now(UTC)
    if _master_cache is not None and now - _master_cache[0] < _MASTER_TTL:
        return _master_cache[1]
    names: dict[str, str] = {}
    try:
        async with async_session_factory() as session:
            for symbol, name in (
                await session.execute(select(FundamentalSnapshot.symbol, FundamentalSnapshot.name))
            ).all():
                names.setdefault(symbol.upper(), name or "")
            for (symbol,) in (
                await session.execute(
                    select(Instrument.symbol_name).where(Instrument.exchange == "NSE")
                )
            ).all():
                names.setdefault(symbol.upper(), "")
    except Exception:
        logger.info("Symbol master database lookup unavailable")
        return []
    master = [{"symbol": symbol, "name": name} for symbol, name in sorted(names.items())]
    _master_cache = (now, master)
    return master


async def load_candidates_from_db() -> list[dict[str, Any]]:
    """Latest fundamental snapshot per symbol, marked with the latest stored close."""
    settings = get_settings()
    try:
        async with async_session_factory() as session:
            snapshots = (
                await session.scalars(
                    select(FundamentalSnapshot).order_by(FundamentalSnapshot.data_date.desc())
                )
            ).all()
            bars = (
                await session.scalars(select(DailyBar).order_by(DailyBar.bar_time.desc()))
            ).all()
    except Exception:
        logger.info("Research universe database lookup unavailable")
        return []

    latest_bar: dict[str, DailyBar] = {}
    for bar in bars:
        latest_bar.setdefault(bar.symbol.upper(), bar)

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    max_age = timedelta(hours=settings.MARKET_DATA_MAX_AGE_HOURS)
    now = datetime.now(UTC)
    for snap in snapshots:
        symbol = snap.symbol.upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        latest: DailyBar | None = latest_bar.get(symbol)
        price = latest.close if latest is not None else None
        price_time = latest.bar_time if latest is not None else None
        if price_time is not None and price_time.tzinfo is None:
            price_time = price_time.replace(tzinfo=UTC)
        fresh = (
            price_time is not None
            and (now - price_time) <= max_age
            and price is not None
            and price > 0
        )
        pe = None
        if fresh and snap.eps is not None and snap.eps > 0 and price is not None:
            pe = calculate_pe_ratio(price, snap.eps)
        data_date = snap.data_date if snap.data_date.tzinfo else snap.data_date.replace(tzinfo=UTC)
        candidates.append(
            {
                "symbol": symbol,
                "name": snap.name or symbol,
                "asset_type": snap.asset_type,
                "sector": snap.sector,
                "security_id": snap.security_id,
                "market_cap_cr": snap.market_cap_cr,
                "current_price": price if fresh else 0.0,
                "has_price_data": fresh,
                "price_retrieved_at": price_time.isoformat() if price_time else None,
                "pe_ratio": pe,
                "eps": snap.eps,
                "roe_pct": snap.roe_pct,
                "roce_pct": snap.roce_pct,
                "debt_to_equity": snap.debt_to_equity,
                "promoter_pledge_pct": snap.promoter_pledge_pct,
                "revenue_growth_3y_cagr_pct": snap.revenue_growth_3y_cagr_pct,
                "profit_growth_3y_cagr_pct": snap.profit_growth_3y_cagr_pct,
                "source_name": snap.source_name,
                "source_url": snap.source_url,
                "source_type": snap.source_type,
                "data_date": data_date.isoformat(),
                "price_source_name": "INDstocks",
                "price_source_url": INDSTOCKS_PRICE_URL,
            }
        )
    return candidates


async def load_portfolio_from_broker() -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.indstocks_configured:
        return None
    async with IndstocksClient(settings) as client:
        holdings_raw = await client.get_holdings()
        funds = await client.get_funds()
        codes = [
            scrip_code("NSE", str(row.get("security_id")))
            for row in holdings_raw
            if row.get("security_id")
        ]
        prices: dict[str, float] = {}
        for offset in range(0, len(codes), 500):
            prices.update(await client.get_ltp(codes[offset : offset + 500]))
    now = datetime.now(UTC).isoformat()
    holdings: list[dict[str, Any]] = []
    total = 0.0
    for row in holdings_raw:
        security_id = str(row.get("security_id") or "")
        code = scrip_code("NSE", security_id) if security_id else ""
        qty = float(row.get("total_qty") or 0)
        avg = float(row.get("avg_price") or 0)
        price = prices.get(code)
        market_value = qty * price if price is not None else 0.0
        total += market_value
        symbol = str(row.get("symbol") or "").upper()
        holdings.append(
            {
                "symbol": symbol,
                "security_id": security_id,
                "isin": row.get("isin"),
                "quantity": qty,
                "average_buy_price": avg,
                "current_price": price,
                "market_value": market_value,
                "sector": "Unclassified",
                "price_retrieved_at": now if price is not None else None,
                "price_source_name": "INDstocks",
                "price_source_url": "https://api.indstocks.com/market/quotes/ltp",
            }
        )
    cash = equity_cash_available(funds)
    return {
        "cash_available": cash,
        "total_value": round(total + cash, 2),
        "holdings": holdings,
        "portfolio_source": "indstocks",
        "retrieved_at": now,
    }
