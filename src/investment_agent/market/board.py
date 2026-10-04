"""Live NSE movers and candles from INDstocks. Rankings are cached briefly."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from investment_agent.market.indstocks import (
    IndstocksClient,
    IndstocksError,
    scrip_code,
    token_cooldown_active,
)

logger = logging.getLogger(__name__)

PAGE_CAP = 200
QUOTE_BATCH = 80
RANK_TTL = timedelta(seconds=90)
SYMBOL_TTL = timedelta(hours=6)

_lock = asyncio.Lock()
_symbols: dict[str, dict[str, str]] = {}
_symbols_at: datetime | None = None
_ranked: list[dict[str, Any]] = []
_ranked_at: datetime | None = None
_build_task: asyncio.Task[None] | None = None
_progress: dict[str, Any] = {"scanned": 0, "universe": 0, "error": None}

RANGE_WINDOWS = {
    "1d": ("5minute", timedelta(days=1)),
    "1w": ("15minute", timedelta(days=7)),
    "1m": ("1day", timedelta(days=31)),
    "3m": ("1day", timedelta(days=92)),
    "6m": ("1day", timedelta(days=183)),
    "1y": ("1day", timedelta(days=365)),
    "5y": ("1day", timedelta(days=365 * 5)),
}


def rank_movers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Largest absolute session move first. Ties keep the higher traded volume."""
    return sorted(
        rows,
        key=lambda row: (
            abs(float(row.get("day_change_percentage") or 0)),
            float(row.get("volume") or 0),
        ),
        reverse=True,
    )


def page_movers(rows: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    offset = max(offset, 0)
    limit = min(max(limit, 1), 20)
    chunk = rows[offset : offset + limit]
    next_offset = offset + limit if offset + limit < len(rows) else None
    return {
        "items": chunk,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
        "total": len(rows),
    }


def _quote_row(meta: dict[str, str], quote: dict[str, Any]) -> dict[str, Any] | None:
    price = quote.get("live_price")
    if price is None:
        return None
    return {
        "symbol": meta["symbol_name"],
        "name": meta.get("trading_symbol") or meta["symbol_name"],
        "security_id": meta["security_id"],
        "scrip_code": scrip_code(meta["exchange"], meta["security_id"]),
        "live_price": float(price),
        "day_change": float(quote.get("day_change") or 0),
        "day_change_percentage": float(quote.get("day_change_percentage") or 0),
        "day_open": quote.get("day_open"),
        "day_high": quote.get("day_high"),
        "day_low": quote.get("day_low"),
        "prev_close": quote.get("prev_close"),
        "volume": float(quote.get("volume") or 0),
    }


async def _load_symbols(client: IndstocksClient) -> dict[str, dict[str, str]]:
    global _symbols, _symbols_at
    now = datetime.now(UTC)
    if _symbols and _symbols_at and now - _symbols_at < SYMBOL_TTL:
        return _symbols
    instruments = await client.get_equity_instruments()
    mapped: dict[str, dict[str, str]] = {}
    for row in instruments:
        if row["exchange"] != "NSE":
            continue
        mapped[row["symbol_name"]] = row
    _symbols = mapped
    _symbols_at = now
    return mapped


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def _build_rankings() -> None:
    """Quote NSE equities in small batches and publish movers as each batch lands."""
    global _ranked, _ranked_at, _progress
    collected: list[dict[str, Any]] = []
    try:
        async with IndstocksClient() as client:
            symbols = await _load_symbols(client)
            by_code = {
                scrip_code(row["exchange"], row["security_id"]): row for row in symbols.values()
            }
            codes = list(by_code)
            _progress = {"scanned": 0, "universe": len(codes), "error": None}
            for batch in _chunks(codes, QUOTE_BATCH):
                quotes = await client.get_quotes(batch)
                for code, quote in quotes.items():
                    meta = by_code.get(code)
                    if meta is None or not isinstance(quote, dict):
                        continue
                    row = _quote_row(meta, quote)
                    if row is not None:
                        collected.append(row)
                _ranked = rank_movers(collected)[:PAGE_CAP]
                _ranked_at = datetime.now(UTC)
                _progress["scanned"] = min(_progress["scanned"] + len(batch), len(codes))
        logger.info("Ranked %s NSE movers from %s symbols", len(_ranked), _progress["universe"])
    except Exception as exc:
        _progress["error"] = str(exc)
        logger.info("NSE mover scan stopped: %s", exc)


def _ensure_build() -> None:
    global _build_task
    fresh = (
        _ranked_at is not None
        and datetime.now(UTC) - _ranked_at < RANK_TTL
        and _progress.get("scanned", 0) >= _progress.get("universe", 1)
        and not _progress.get("error")
    )
    if fresh:
        return
    if token_cooldown_active():
        _progress["error"] = (
            "INDstocks allows one login token per minute. Wait a minute, then press Sync."
        )
        return
    if _build_task is not None and not _build_task.done():
        return
    _progress["error"] = None
    _build_task = asyncio.create_task(_build_rankings())


async def trending_board(offset: int = 0, limit: int = 5, exchange: str = "NSE") -> dict[str, Any]:
    from investment_agent.market.yahoo_market import MarketDataError, screen_movers

    limit = min(max(limit, 1), 20)
    offset = max(offset, 0)
    venue = "BSE" if exchange.upper() == "BSE" else "NSE"
    try:
        rows, total = await screen_movers(offset, limit, venue)
    except MarketDataError as exc:
        raise IndstocksError(str(exc)) from exc
    next_offset = offset + limit if offset + limit < total else None
    return {
        "items": rows,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
        "total": total,
        "pending": False,
        "scanned": offset + len(rows),
        "universe": total,
        "as_of": datetime.now(UTC).isoformat(),
    }


async def quote_for_symbol(symbol: str, exchange: str = "NSE") -> dict[str, Any] | None:
    from investment_agent.market.yahoo_market import MarketDataError, quote_symbol

    try:
        return await quote_symbol(symbol, exchange)
    except MarketDataError as exc:
        raise IndstocksError(str(exc)) from exc


async def history_for_symbol(symbol: str, range_key: str, exchange: str = "NSE") -> dict[str, Any] | None:
    from investment_agent.market.yahoo_market import CHART_RANGES, MarketDataError, chart_symbol

    if range_key not in CHART_RANGES:
        raise ValueError(f"Unsupported range {range_key}")
    try:
        return await chart_symbol(symbol, range_key, exchange)
    except MarketDataError as exc:
        raise IndstocksError(str(exc)) from exc


async def live_indices() -> list[dict[str, Any]]:
    from investment_agent.market.yahoo_market import MarketDataError, index_quotes

    try:
        return await index_quotes()
    except MarketDataError as exc:
        raise IndstocksError(str(exc)) from exc
