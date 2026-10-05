"""Pull INDstocks prices, holdings, and AMFI NAVs into Postgres."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from investment_agent.config.settings import Settings, get_settings
from investment_agent.db.models.base import utc_now
from investment_agent.db.models.market import (
    DailyBar,
    EvidenceRecord,
    Instrument,
    MutualFundScheme,
    NavRecord,
)
from investment_agent.db.models.portfolio import Holding, Portfolio
from investment_agent.db.models.user import User
from investment_agent.db.session import async_session_factory
from investment_agent.market.amfi import fetch_nav_file, parse_nav_file
from investment_agent.market.indstocks import (
    IndstocksClient,
    IndstocksError,
    equity_cash_available,
    scrip_code,
)

logger = logging.getLogger(__name__)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def sync_mutual_fund_schemes(settings: Settings | None = None) -> dict[str, Any]:
    """Workstream B, B1: load the full AMFI scheme master (every scheme, not just the
    watchlist in AMFI_SCHEME_CODES) and upsert it with the derived plan/option/sebi_group
    classification. Free and keyless, so — like `sync_fundamentals` — this does not require
    INDstocks to be configured.
    """
    settings = settings or get_settings()
    result: dict[str, Any] = {"synced": 0, "warnings": []}
    try:
        text = await fetch_nav_file(settings.AMFI_NAV_URL)
    except Exception as exc:
        result["warnings"].append(f"AMFI scheme master download failed: {exc}")
        return result

    rows = parse_nav_file(text, scheme_codes=None)
    if not rows:
        result["warnings"].append("AMFI scheme master returned no parsable rows.")
        return result

    now = utc_now()
    async with async_session_factory() as session:
        for row in rows:
            # parse_nav_file's return type is intentionally the loose dict[str, object]
            # shared with the pre-existing NAV-record parsing below; narrow the one field
            # that needs a numeric operation rather than widening that shared signature.
            nav_value = cast(float, row["nav"])
            stmt = pg_insert(MutualFundScheme).values(
                scheme_code=str(row["scheme_code"]),
                name=str(row["scheme_name"]),
                isin=row.get("isin"),
                fund_house=row.get("fund_house"),
                category=row.get("category"),
                sebi_group=row.get("sebi_group"),
                plan=row.get("plan"),
                option=row.get("option"),
                latest_nav=nav_value,
                nav_date=row["nav_date"],
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["scheme_code"],
                set_={
                    "name": str(row["scheme_name"]),
                    "isin": row.get("isin"),
                    "fund_house": row.get("fund_house"),
                    "category": row.get("category"),
                    "sebi_group": row.get("sebi_group"),
                    "plan": row.get("plan"),
                    "option": row.get("option"),
                    "latest_nav": nav_value,
                    "nav_date": row["nav_date"],
                    "updated_at": now,
                },
            )
            await session.execute(stmt)
        await session.commit()
    result["synced"] = len(rows)
    return result


async def sync_fundamentals(
    settings: Settings | None = None, symbols: list[str] | None = None
) -> dict[str, Any]:
    """Gap 2: automatic fundamentals ingest — Yahoo financial statements + NSE shareholding.

    Free and keyless, so unlike the rest of this module it does **not** require INDstocks
    to be configured — `refresh_market_data` calls this before the broker-specific gate so
    fundamentals sync for users who haven't connected a broker yet. ROCE, FCF, and
    revenue/profit CAGR are computed in `portfolio/calculations.py` (never by the LLM);
    anything the source doesn't provide stays None (DATA_UNAVAILABLE), never guessed.
    """
    from investment_agent.market.fundamentals import store_fundamental_snapshots
    from investment_agent.market.nse import get_shareholding, latest_promoter_pledge_pct
    from investment_agent.market.yahoo_market import (
        company_fundamentals,
        financial_statement_history,
    )
    from investment_agent.portfolio.calculations import derive_ratios_from_statements
    from investment_agent.research.evidence import SourceType

    settings = settings or get_settings()
    target_symbols = symbols if symbols is not None else settings.indstocks_watchlist
    result: dict[str, Any] = {"synced": 0, "warnings": []}
    if not target_symbols:
        result["warnings"].append(
            "No watchlist symbols configured (INDSTOCKS_WATCHLIST); fundamentals auto-ingest skipped."
        )
        return result

    now = utc_now()
    rows: list[dict[str, Any]] = []
    for symbol in target_symbols:
        try:
            fundamentals = await company_fundamentals(symbol, "NSE")
            statements = await financial_statement_history(symbol, "NSE")
        except Exception as exc:
            result["warnings"].append(f"{symbol}: Yahoo fundamentals fetch failed ({exc})")
            continue
        if not fundamentals:
            result["warnings"].append(f"{symbol}: DATA_UNAVAILABLE from Yahoo company profile")
            continue

        ratios = derive_ratios_from_statements(statements)
        try:
            shareholding = await get_shareholding(symbol)
            pledge_pct = latest_promoter_pledge_pct(shareholding)
        except Exception:
            pledge_pct = None

        rows.append(
            {
                "symbol": symbol,
                "name": symbol,
                "sector": fundamentals.get("sector") or "Unclassified",
                "asset_type": "stock",
                "data_date": now,
                "roe_pct": fundamentals.get("roe_pct"),
                "roce_pct": ratios.get("roce_pct"),
                "debt_to_equity": fundamentals.get("debt_to_equity"),
                "promoter_pledge_pct": pledge_pct,
                "revenue_growth_3y_cagr_pct": ratios.get("revenue_growth_3y_cagr_pct"),
                "profit_growth_3y_cagr_pct": ratios.get("profit_growth_3y_cagr_pct"),
                "eps": fundamentals.get("eps"),
                "book_value_per_share": fundamentals.get("book_value"),
                "market_cap_cr": None,
                # No dedicated FCF column on FundamentalSnapshot yet; carried in raw_payload
                # (store_fundamental_snapshots persists the whole row there) rather than
                # forcing a migration mid-step.
                "fcf_cr": ratios.get("fcf"),
                "source_name": "Yahoo Finance financial statements",
                "source_url": f"https://finance.yahoo.com/quote/{symbol}.NS/financials",
                "source_type": SourceType.FINANCIAL_DATA_PROVIDER.value,
            }
        )

    if rows:
        result["synced"] = await store_fundamental_snapshots(rows)
    return result


async def refresh_market_data(
    settings: Settings | None = None, include_amfi: bool = True
) -> dict[str, Any]:
    settings = settings or get_settings()
    summary: dict[str, Any] = {
        "instruments": 0,
        "quotes": 0,
        "daily_bars": 0,
        "holdings": 0,
        "nav_records": 0,
        "fundamentals_synced": 0,
        "mutual_fund_schemes_synced": 0,
        "warnings": [],
    }

    try:
        fundamentals_result = await sync_fundamentals(settings)
        summary["fundamentals_synced"] = fundamentals_result.get("synced", 0)
        summary["warnings"].extend(fundamentals_result.get("warnings", []))
    except Exception as exc:
        summary["warnings"].append(f"Fundamentals auto-ingest failed: {exc}")

    try:
        scheme_result = await sync_mutual_fund_schemes(settings)
        summary["mutual_fund_schemes_synced"] = scheme_result.get("synced", 0)
        summary["warnings"].extend(scheme_result.get("warnings", []))
    except Exception as exc:
        summary["warnings"].append(f"Mutual fund scheme master sync failed: {exc}")

    if not settings.indstocks_configured:
        raise IndstocksError(
            "INDstocks is not configured. Set INDSTOCKS_ACCESS_TOKEN, "
            "or INDSTOCKS_CLIENT_ID, INDSTOCKS_MPIN, and INDSTOCKS_TOTP_SECRET."
        )
    watchlist = set(settings.indstocks_watchlist)
    async with IndstocksClient(settings) as client:
        instruments = await client.get_equity_instruments()
        selected = [
            row
            for row in instruments
            if row["exchange"] == "NSE" and (not watchlist or row["symbol_name"] in watchlist)
        ]
        if watchlist:
            found = {row["symbol_name"] for row in selected}
            missing = sorted(watchlist - found)
            if missing:
                summary["warnings"].append(
                    f"Watchlist symbols missing from NSE EQ master: {', '.join(missing)}"
                )
        holdings_raw = await client.get_holdings()
        funds = await client.get_funds()
        holding_ids = {
            str(row.get("security_id")) for row in holdings_raw if row.get("security_id")
        }
        by_security = {row["security_id"]: row for row in instruments if row["exchange"] == "NSE"}
        for security_id in holding_ids:
            row = by_security.get(security_id)
            if row and row not in selected:
                selected.append(row)

        codes = [scrip_code(row["exchange"], row["security_id"]) for row in selected]
        quotes: dict[str, dict[str, Any]] = {}
        for batch in _chunks(codes, 500):
            quotes.update(await client.get_quotes(batch))
        summary["quotes"] = len(quotes)

        end = datetime.now(UTC)
        start = end - timedelta(days=370)
        bars_by_code: dict[str, list[dict[str, Any]]] = {}
        for batch in _chunks(codes, 5):
            bars_by_code.update(await client.get_daily_bars(batch, start, end))

    nav_rows: list[dict[str, object]] = []
    if include_amfi and settings.amfi_scheme_codes:
        try:
            text = await fetch_nav_file(settings.AMFI_NAV_URL)
            nav_rows = parse_nav_file(text, set(settings.amfi_scheme_codes))
        except Exception as exc:
            summary["warnings"].append(f"AMFI NAV download failed: {exc}")
    elif include_amfi:
        summary["warnings"].append("AMFI_SCHEME_CODES is empty; mutual fund NAVs were not stored.")

    now = utc_now()
    async with async_session_factory() as session:
        for row in selected:
            stmt = pg_insert(Instrument).values(
                id=_new_id(),
                exchange=row["exchange"],
                segment=row["segment"],
                security_id=row["security_id"],
                trading_symbol=row["trading_symbol"],
                symbol_name=row["symbol_name"],
                series=row["series"],
                instrument_name=row["instrument_name"],
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_instrument_exchange_security",
                set_={
                    "trading_symbol": row["trading_symbol"],
                    "symbol_name": row["symbol_name"],
                    "series": row["series"],
                    "updated_at": now,
                },
            )
            await session.execute(stmt)
        summary["instruments"] = len(selected)

        symbol_by_code = {scrip_code(row["exchange"], row["security_id"]): row for row in selected}
        bar_count = 0
        for code, candles in bars_by_code.items():
            meta = symbol_by_code.get(code)
            if meta is None:
                continue
            for candle in candles:
                ts = candle.get("ts")
                if ts is None:
                    continue
                bar_time = datetime.fromtimestamp(int(ts), tz=UTC)
                stmt = pg_insert(DailyBar).values(
                    id=_new_id(),
                    security_id=meta["security_id"],
                    scrip_code=code,
                    symbol=meta["symbol_name"],
                    bar_time=bar_time,
                    open=float(candle.get("o") or 0),
                    high=float(candle.get("h") or 0),
                    low=float(candle.get("l") or 0),
                    close=float(candle.get("c") or 0),
                    volume=float(candle.get("v") or 0),
                    created_at=now,
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_daily_bar_security_time",
                    set_={
                        "open": float(candle.get("o") or 0),
                        "high": float(candle.get("h") or 0),
                        "low": float(candle.get("l") or 0),
                        "close": float(candle.get("c") or 0),
                        "volume": float(candle.get("v") or 0),
                        "updated_at": now,
                    },
                )
                await session.execute(stmt)
                bar_count += 1
        summary["daily_bars"] = bar_count

        for nav_row in nav_rows:
            nav_value = cast(float, nav_row["nav"])
            stmt = pg_insert(NavRecord).values(
                id=_new_id(),
                scheme_code=str(nav_row["scheme_code"]),
                scheme_name=str(nav_row["scheme_name"]),
                isin=nav_row.get("isin"),
                nav=float(nav_value),
                nav_date=nav_row["nav_date"],
                source_url=settings.AMFI_NAV_URL,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_nav_scheme_date",
                set_={
                    "nav": float(nav_value),
                    "scheme_name": str(nav_row["scheme_name"]),
                    "updated_at": now,
                },
            )
            await session.execute(stmt)
        summary["nav_records"] = len(nav_rows)

        stored = await _replace_broker_holdings(
            session, holdings_raw, quotes, equity_cash_available(funds), now
        )
        summary["holdings"] = len(holdings_raw)
        if holdings_raw and not stored:
            summary["warnings"].append(
                "Holdings were fetched but not stored. Create a user row before refresh to attach a portfolio."
            )
        await session.commit()
    return summary


async def _replace_broker_holdings(
    session: Any,
    holdings_raw: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
    cash: float,
    now: datetime,
) -> bool:
    user = await session.scalar(select(User).limit(1))
    if user is None:
        return False
    portfolio = await session.scalar(select(Portfolio).where(Portfolio.user_id == user.id))
    if portfolio is None:
        portfolio = Portfolio(
            user_id=user.id,
            name="INDstocks",
            cash_available=cash,
            currency="INR",
            created_at=now,
            updated_at=now,
        )
        session.add(portfolio)
        await session.flush()
    portfolio.cash_available = cash
    portfolio.updated_at = now
    existing = (
        await session.scalars(select(Holding).where(Holding.portfolio_id == portfolio.id))
    ).all()
    for row in existing:
        await session.delete(row)
    for raw in holdings_raw:
        security_id = str(raw.get("security_id") or "")
        code = scrip_code("NSE", security_id) if security_id else ""
        quote = quotes.get(code) or {}
        price = float(quote["live_price"]) if quote.get("live_price") is not None else 0.0
        symbol = str(raw.get("symbol") or security_id).upper()
        session.add(
            Holding(
                portfolio_id=portfolio.id,
                asset_id=symbol,
                security_id=security_id or None,
                isin=raw.get("isin"),
                asset_type="stock",
                symbol=symbol,
                name=symbol,
                sector="Unclassified",
                quantity=float(raw.get("total_qty") or 0),
                average_buy_price=float(raw.get("avg_price") or 0),
                current_price=price,
                metadata_info={"price_source": "INDstocks", "scrip_code": code},
                created_at=now,
                updated_at=now,
            )
        )
        if price > 0:
            session.add(
                EvidenceRecord(
                    symbol=symbol,
                    claim=f"{symbol} last traded price {price}",
                    source_name="INDstocks",
                    source_url="https://api.indstocks.com/market/quotes/full",
                    source_type="INDstocks",
                    retrieved_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
    return True


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())
