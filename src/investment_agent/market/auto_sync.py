"""Background market-data sync, started from the app lifespan.

On startup the task checks whether the database is empty or older than
`MARKET_DATA_MAX_AGE_HOURS` and, if so, syncs straight away. After that it wakes every few
minutes and syncs again when the data has aged by `MARKET_SYNC_INTERVAL_HOURS` while the NSE is
open, or once after each close so the stored prices are the closing ones. Weekends and nights
therefore cost nothing.

The task never blocks startup and never raises: every failure is logged and the loop keeps
going. Stock prices and ratios come from `live_universe` (the same single shared fetch the chat
uses when it needs data right now); the mutual-fund scheme master comes from AMFI; and if
INDstocks is configured its instruments and daily bars are pulled too.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from investment_agent.config.settings import get_settings
from investment_agent.market import live_universe
from investment_agent.market.indstocks import IndstocksError

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
CHECK_INTERVAL_SECONDS = 15 * 60


@dataclass
class SyncState:
    in_progress: bool = False
    last_sync_at: datetime | None = None
    last_error: str | None = None


state = SyncState()
_task: asyncio.Task[None] | None = None


def is_market_open(now: datetime) -> bool:
    local = now.astimezone(IST)
    return local.weekday() < 5 and MARKET_OPEN <= local.time() < MARKET_CLOSE


def last_market_close(now: datetime) -> datetime:
    """The most recent 15:30 IST close of a weekday that is at or before `now`."""
    local = now.astimezone(IST)
    day = local.date()
    if local.time() < MARKET_CLOSE:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return datetime.combine(day, MARKET_CLOSE, tzinfo=IST)


def should_sync(now: datetime, last_sync_at: datetime | None, interval: timedelta) -> bool:
    """Market-hours-aware schedule: while the market is open, every `interval`; otherwise
    only if the last sync happened before the latest close."""
    if last_sync_at is None:
        return True
    if is_market_open(now):
        return now - last_sync_at >= interval
    return last_sync_at < last_market_close(now)


async def table_counts() -> dict[str, int | None]:
    """Row counts for the tables the chat depends on (None when the database is unreachable)."""
    from investment_agent.db.models.market import (
        DailyBar,
        FundamentalSnapshot,
        MutualFundScheme,
        NavRecord,
    )
    from investment_agent.db.session import async_session_factory

    counts: dict[str, int | None] = {}
    tables: dict[str, Any] = {
        "fundamental_snapshots": FundamentalSnapshot,
        "daily_bars": DailyBar,
        "mutual_fund_schemes": MutualFundScheme,
        "nav_records": NavRecord,
    }
    try:
        async with async_session_factory() as session:
            for name, model in tables.items():
                counts[name] = int(await session.scalar(select(func.count()).select_from(model)) or 0)
    except Exception as exc:
        logger.info("Table counts unavailable: %s", exc)
        return dict.fromkeys(tables)
    return counts


async def latest_data_at() -> datetime | None:
    """When the newest stored fundamentals/bars were written (None when empty or unreachable)."""
    from investment_agent.db.models.market import DailyBar, FundamentalSnapshot
    from investment_agent.db.session import async_session_factory

    try:
        async with async_session_factory() as session:
            newest = [
                await session.scalar(select(func.max(FundamentalSnapshot.data_date))),
                await session.scalar(select(func.max(DailyBar.bar_time))),
            ]
    except Exception as exc:
        logger.info("Stored data age unavailable: %s", exc)
        return None
    dates = [d if d.tzinfo else d.replace(tzinfo=UTC) for d in newest if d is not None]
    return min(dates) if len(dates) == len(newest) else None


async def needs_initial_sync() -> bool:
    """True when the database is empty (or unreachable) or older than the max age."""
    newest = await latest_data_at()
    if newest is None:
        return True
    return datetime.now(UTC) - newest > timedelta(hours=get_settings().MARKET_DATA_MAX_AGE_HOURS)


async def run_sync_once() -> None:
    """One full sync. Never raises."""
    if state.in_progress:
        return
    state.in_progress = True
    errors: list[str] = []
    try:
        from investment_agent.market.sync import refresh_market_data, sync_mutual_fund_schemes

        try:
            # Syncs the watchlist's fundamentals and the AMFI scheme master first, then
            # raises IndstocksError when no broker is configured: expected, not a failure.
            await refresh_market_data()
        except IndstocksError:
            logger.info("INDstocks not configured: using Yahoo/TradingView data for stock prices")
        except Exception as exc:
            errors.append(f"refresh_market_data: {exc}")
            logger.warning("Market refresh failed: %s", exc)
            try:
                await sync_mutual_fund_schemes()
            except Exception as scheme_exc:
                errors.append(f"sync_mutual_fund_schemes: {scheme_exc}")
                logger.warning("Mutual fund scheme sync failed: %s", scheme_exc)

        task = live_universe.start_refresh(force=True)
        if task is not None:
            try:
                await task
            except Exception as exc:
                errors.append(f"live universe: {exc}")
        state.last_error = "; ".join(errors) or None
        if not errors or live_universe.has_result():
            state.last_sync_at = datetime.now(UTC)
    except Exception as exc:  # defensive: the loop must survive anything
        state.last_error = str(exc)
        logger.exception("Market sync crashed")
    finally:
        state.in_progress = False


async def sync_loop() -> None:
    interval = timedelta(hours=get_settings().MARKET_SYNC_INTERVAL_HOURS)
    try:
        if await needs_initial_sync():
            logger.info("Market data is missing or stale: syncing in the background")
            await run_sync_once()
        else:
            state.last_sync_at = await latest_data_at()
        while True:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            if should_sync(datetime.now(UTC), state.last_sync_at, interval):
                await run_sync_once()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Market sync loop stopped unexpectedly")


def start_background_sync() -> asyncio.Task[None] | None:
    """Start the sync loop (idempotent). Returns None when auto-sync is disabled."""
    global _task
    settings = get_settings()
    if not settings.MARKET_AUTO_SYNC_ENABLED or settings.APP_ENV == "test":
        return None
    if _task is None or _task.done():
        _task = asyncio.create_task(sync_loop(), name="market-auto-sync")
    return _task


async def stop_background_sync() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await _task
        _task = None
