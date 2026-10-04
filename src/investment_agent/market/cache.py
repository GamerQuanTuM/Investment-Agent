import logging

from investment_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


async def cache_get(key: str) -> str | None:
    try:
        from redis.asyncio import Redis

        settings = get_settings()
        client = Redis.from_url(
            settings.resolved_redis_url,
            socket_connect_timeout=20,
            socket_timeout=20,
        )
        try:
            value = await client.get(key)
            if value is None:
                return None
            return value.decode() if isinstance(value, bytes) else str(value)
        finally:
            await client.aclose()
    except Exception:
        logger.debug("Redis cache read skipped for %s", key)
        return None


async def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    try:
        from redis.asyncio import Redis

        settings = get_settings()
        client = Redis.from_url(
            settings.resolved_redis_url,
            socket_connect_timeout=20,
            socket_timeout=20,
        )
        try:
            await client.set(key, value, ex=ttl_seconds)
        finally:
            await client.aclose()
    except Exception:
        logger.debug("Redis cache write skipped for %s", key)
