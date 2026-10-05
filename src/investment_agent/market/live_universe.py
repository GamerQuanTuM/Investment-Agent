"""Build the stock picker's candidate universe live, from the market providers.

The picker normally reads stored fundamentals and daily bars. Until the first background sync
has filled those tables (or if it keeps failing), `get_candidates` fetches a reviewed list of
Nifty 50 / Nifty Next 50 names directly: price history and quote from Yahoo, company ratios
from Yahoo (gaps filled from TradingView), ROCE and growth computed in
`portfolio/calculations.py`. The names are then scored by exactly the same code as the stored
data (`portfolio.stock_picker.build_candidates`).

Only one fetch ever runs at a time. A chat request waits a bounded time for it and otherwise
reports "still loading", and the next request (or the "Try again" chip) picks up the result.
Whatever was fetched is stored back to the database so the next request is instant.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from investment_agent.config.settings import get_settings
from investment_agent.market.cache import CacheTTL, cache_get, cache_set
from investment_agent.market.index_constituents import candidate_symbols
from investment_agent.portfolio.calculations import derive_ratios_from_statements
from investment_agent.portfolio.stock_picker import (
    Candidate,
    build_candidates,
    invalidate_universe_cache,
)

logger = logging.getLogger(__name__)

PRICE_SOURCE = ("Yahoo Finance price history", "https://finance.yahoo.com")
FUNDAMENTALS_SOURCE = "Yahoo Finance company profile and statements"
RESULT_TTL = timedelta(seconds=int(CacheTTL.LIVE_UNIVERSE))
FAILURE_COOLDOWN = timedelta(seconds=120)
ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.5
MIN_CANDIDATES = 3  # fewer than this is not a usable universe

Series = list[tuple[datetime, float, float]]


@dataclass
class LiveOutcome:
    status: Literal["ready", "loading", "failed"]
    candidates: list[Candidate]


@dataclass
class _Result:
    at: datetime
    candidates: list[Candidate]


class _State:
    task: asyncio.Task[list[Candidate]] | None = None
    result: _Result | None = None
    failed_at: datetime | None = None


_state = _State()


def reset_state() -> None:
    """Forget every in-memory result (tests, and after a settings change)."""
    if _state.task is not None and not _state.task.done():
        _state.task.cancel()
    _state.task = None
    _state.result = None
    _state.failed_at = None


def has_result() -> bool:
    return _state.result is not None


def is_loading() -> bool:
    return _state.task is not None and not _state.task.done()


# ----------------------------------------------------------------------- fetching


async def _bounded[T](call: Callable[[], Awaitable[T]], timeout: float) -> T | None:
    """Run one provider call with a timeout and retries. None when it never succeeds."""
    for attempt in range(ATTEMPTS):
        try:
            return await asyncio.wait_for(call(), timeout=timeout)
        except Exception as exc:
            logger.debug("Provider call failed (attempt %d/%d): %s", attempt + 1, ATTEMPTS, exc)
            if attempt + 1 < ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
    return None


def _snapshot(
    symbol: str, quote: dict[str, Any], fundamentals: dict[str, Any], ratios: dict[str, Any]
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "name": quote.get("name") or symbol,
        "sector": fundamentals.get("sector") or "Unclassified",
        "asset_type": "stock",
        "eps": fundamentals.get("eps"),
        "book_value_per_share": fundamentals.get("book_value"),
        "roe_pct": fundamentals.get("roe_pct"),
        "roce_pct": ratios.get("roce_pct"),
        "debt_to_equity": fundamentals.get("debt_to_equity"),
        "promoter_pledge_pct": None,
        "revenue_growth_3y_cagr_pct": ratios.get("revenue_growth_3y_cagr_pct"),
        "profit_growth_3y_cagr_pct": ratios.get("profit_growth_3y_cagr_pct"),
        "market_cap_cr": quote.get("market_cap_cr"),
        "data_date": datetime.now(UTC).isoformat(),
        "source_name": fundamentals.get("source") or FUNDAMENTALS_SOURCE,
        "source_url": f"https://finance.yahoo.com/quote/{symbol}.NS",
        "source_type": "Financial Data Provider",
    }


def _series_from_chart(chart: dict[str, Any]) -> Series:
    bars: Series = []
    for candle in chart.get("candles") or []:
        close = candle.get("close")
        if close and close > 0:
            bars.append(
                (datetime.fromtimestamp(int(candle["ts"]), tz=UTC), float(close), float(candle.get("volume") or 0))
            )
    return bars


async def _fill_gaps_from_tradingview(symbol: str, fundamentals: dict[str, Any], timeout: float) -> dict[str, Any]:
    """TradingView supplies ROE / debt when Yahoo has none; Yahoo's own figures always win."""
    if fundamentals.get("roe_pct") is not None and fundamentals.get("debt_to_equity") is not None:
        return fundamentals
    from investment_agent.market.tradingview import merge_fundamentals, tradingview_fundamentals

    extra = await _bounded(lambda: asyncio.to_thread(tradingview_fundamentals, symbol), timeout)
    return merge_fundamentals(fundamentals, extra) if extra else fundamentals


async def _fetch_symbol(symbol: str, timeout: float) -> tuple[dict[str, Any], Series] | None:
    """One symbol's snapshot + price series, from the 1h cache when present. None when the
    providers have no usable data for it (it is then simply left out, never guessed)."""
    from investment_agent.market.yahoo_market import (
        chart_symbol,
        company_fundamentals,
        financial_statement_history,
        quote_symbol,
    )

    cache_key = f"live:snapshot:{symbol}"
    cached = await cache_get(cache_key)
    if cached is not None:
        try:
            payload = json.loads(cached)
            return payload["snapshot"], [
                (datetime.fromisoformat(t), float(c), float(v)) for t, c, v in payload["bars"]
            ]
        except (ValueError, KeyError, TypeError):
            logger.debug("Discarding unreadable live snapshot cache for %s", symbol)

    quote, chart, fundamentals = await asyncio.gather(
        _bounded(lambda: quote_symbol(symbol, "NSE"), timeout),
        _bounded(lambda: chart_symbol(symbol, "1y", "NSE"), timeout),
        _bounded(lambda: company_fundamentals(symbol, "NSE"), timeout),
    )
    if not quote or not chart or not fundamentals:
        return None
    bars = _series_from_chart(chart)
    if not bars:
        return None
    statements = await _bounded(lambda: financial_statement_history(symbol, "NSE"), timeout) or {}
    fundamentals = await _fill_gaps_from_tradingview(symbol, fundamentals, timeout)
    snapshot = _snapshot(symbol, quote, fundamentals, derive_ratios_from_statements(statements))
    await cache_set(
        cache_key,
        json.dumps({"snapshot": snapshot, "bars": [[t.isoformat(), c, v] for t, c, v in bars]}),
        CacheTTL.LIVE_UNIVERSE,
    )
    return snapshot, bars


async def fetch_snapshots(
    symbols: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Series]]:
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, settings.LIVE_UNIVERSE_CONCURRENCY))
    timeout = settings.LIVE_UNIVERSE_CALL_TIMEOUT_SECONDS

    async def one(symbol: str) -> tuple[str, tuple[dict[str, Any], Series] | None]:
        async with semaphore:
            try:
                return symbol, await _fetch_symbol(symbol, timeout)
            except Exception as exc:
                logger.info("Live data for %s skipped: %s", symbol, exc)
                return symbol, None

    results = await asyncio.gather(*(one(s) for s in (symbols or candidate_symbols())))
    snapshots: dict[str, dict[str, Any]] = {}
    series: dict[str, Series] = {}
    for symbol, found in results:
        if found is not None:
            snapshots[symbol], series[symbol] = found
    return snapshots, series


# ------------------------------------------------------------------------ persistence


async def persist(snapshots: dict[str, dict[str, Any]], series: dict[str, Series]) -> None:
    """Store what was fetched so the next request reads the database. Best effort: a storage
    failure is logged and never loses the in-memory result."""
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from investment_agent.db.models.base import utc_now
        from investment_agent.db.models.market import DailyBar
        from investment_agent.db.session import async_session_factory
        from investment_agent.market.fundamentals import store_fundamental_snapshots
        from investment_agent.market.universe import invalidate_master_cache

        await store_fundamental_snapshots(list(snapshots.values()))
        if not get_settings().indstocks_configured:  # INDstocks bars, when present, own the series
            now = utc_now()
            rows = [
                {
                    "id": f"yf-{symbol}-{int(t.timestamp())}",
                    "security_id": f"YF:{symbol}",
                    "scrip_code": f"YAHOO:{symbol}",
                    "symbol": symbol,
                    "bar_time": t,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": volume,
                    "created_at": now,
                    "updated_at": now,
                }
                for symbol, bars in series.items()
                for t, close, volume in bars
            ]
            async with async_session_factory() as session:
                for start in range(0, len(rows), 1000):
                    stmt = (
                        pg_insert(DailyBar)
                        .values(rows[start : start + 1000])
                        .on_conflict_do_nothing(constraint="uq_daily_bar_security_time")
                    )
                    await session.execute(stmt)
                await session.commit()
        invalidate_universe_cache()
        invalidate_master_cache()
    except Exception as exc:
        logger.warning("Could not store live market data (continuing in memory): %s", exc)


# ----------------------------------------------------------------------------- refresh


async def refresh() -> list[Candidate]:
    """Fetch, score and store the live universe. Raises RuntimeError if too little came back."""
    snapshots, series = await fetch_snapshots()
    if len(snapshots) < MIN_CANDIDATES:
        raise RuntimeError(f"Market data providers returned data for only {len(snapshots)} stocks")
    candidates = build_candidates(snapshots, series, datetime.now(UTC), price_source=PRICE_SOURCE)
    await persist(snapshots, series)
    return candidates


def _run() -> asyncio.Task[list[Candidate]]:
    async def work() -> list[Candidate]:
        try:
            candidates = await refresh()
        except Exception as exc:
            _state.failed_at = datetime.now(UTC)
            logger.warning("Live universe refresh failed: %s", exc)
            raise
        _state.result = _Result(datetime.now(UTC), candidates)
        _state.failed_at = None
        return candidates

    task = asyncio.create_task(work())
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # failure is already logged
    return task


def start_refresh(*, force: bool = False) -> asyncio.Task[list[Candidate]] | None:
    """Start the single shared fetch (None if a fresh result already exists)."""
    if is_loading():
        return _state.task
    if not force and _state.result and datetime.now(UTC) - _state.result.at < RESULT_TTL:
        return None
    _state.task = _run()
    return _state.task


async def get_candidates(wait_seconds: float | None = None) -> LiveOutcome:
    """The live universe if it is (or soon will be) ready.

    "ready": candidates are scored and usable. "loading": a fetch is still running after
    `wait_seconds`. "failed": the last fetch failed and no result exists.
    """
    now = datetime.now(UTC)
    if _state.result and now - _state.result.at < RESULT_TTL and not is_loading():
        return LiveOutcome("ready", _state.result.candidates)
    if not is_loading():
        if _state.failed_at and now - _state.failed_at < FAILURE_COOLDOWN:
            return LiveOutcome("failed", [])
        start_refresh()
    task = _state.task
    if task is None:
        return LiveOutcome("failed", [])
    wait = get_settings().LIVE_UNIVERSE_WAIT_SECONDS if wait_seconds is None else wait_seconds
    done, _ = await asyncio.wait({task}, timeout=wait)
    if not done:
        return LiveOutcome("loading", [])
    if task.cancelled() or task.exception() is not None:
        return LiveOutcome("failed", [])
    return LiveOutcome("ready", task.result())
