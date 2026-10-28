"""Tavily web search: relevance-ranked results, used for news where Google News RSS is thin.

Never raises: a missing key, timeout or API error returns an empty list so callers fall back.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from investment_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)


async def tavily_search(
    query: str,
    *,
    topic: str = "news",
    max_results: int = 10,
    days: int = 7,
    include_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Results as {title, url, content, score, published_date?}, best first."""
    key = get_settings().TAVILY_API_KEY
    query = query.strip()
    if not key or not query:
        return []
    body: dict[str, Any] = {
        "query": query,
        "topic": topic,
        "search_depth": "basic",
        "max_results": max_results,
    }
    if topic == "news":
        body["days"] = days
    if include_domains:
        body["include_domains"] = include_domains
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                TAVILY_URL, json=body, headers={"Authorization": f"Bearer {key}"}
            )
        if response.status_code >= 400:
            logger.info("Tavily returned %s for %r", response.status_code, query)
            return []
        results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Tavily search failed for %r: %s", query, exc)
        return []
    return [r for r in results if isinstance(r, dict) and r.get("title")]
