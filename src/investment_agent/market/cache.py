"""Shared Redis cache client.

A single connection is opened once from the app lifespan (`init_cache`) and reused for
every get/set, instead of opening and closing a new connection per call. Code paths that
run outside the app lifespan (scripts, tests) still work: `_client()` lazily creates one.

Every cache write should use one of the named `CacheTTL` tiers below rather than a magic
number, so TTL policy for a given kind of data (price vs fundamentals vs filings) stays
consistent across all providers.
"""

from __future__ import annotations

import logging
from enum import IntEnum

from redis.asyncio import Redis

from investment_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


class CacheTTL(IntEnum):
    """Named TTL tiers, in seconds. Pass one of these to `cache_set` instead of a literal."""

    PRICE = 60
    FILINGS = 60 * 60
    FUNDAMENTALS = 24 * 60 * 60
    MF_SEARCH = 60 * 60
    MF_CATALOGUE = 15 * 60
    MF_NAV_HISTORY = 12 * 60 * 60
    NEWS = 30 * 60
    MACRO = 6 * 60 * 60
    CHAT_SESSION = 24 * 60 * 60
    LIVE_UNIVERSE = 60 * 60


def _get_client() -> Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis.from_url(
            settings.resolved_redis_url,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


async def init_cache() -> None:
    """Create the shared client. Call once from the FastAPI lifespan on startup."""
    _get_client()


async def close_cache() -> None:
    """Close the shared client. Call once from the FastAPI lifespan on shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            logger.debug("Redis client close failed, ignoring", exc_info=True)
        _client = None


async def cache_get(key: str) -> str | None:
    try:
        client = _get_client()
        value = await client.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)
    except Exception:
        logger.debug("Redis cache read skipped for %s", key)
        return None


async def cache_set(key: str, value: str, ttl_seconds: int | CacheTTL) -> None:
    try:
        client = _get_client()
        await client.set(key, value, ex=int(ttl_seconds))
    except Exception:
        logger.debug("Redis cache write skipped for %s", key)


async def cache_delete(key: str) -> None:
    try:
        client = _get_client()
        await client.delete(key)
    except Exception:
        logger.debug("Redis cache delete skipped for %s", key)
