"""Google News RSS — free, keyless news search, used for the F4 news-sentiment signal.

Verified live from this environment (confirmed via a direct curl during development,
matching this project's convention of verifying reachability rather than assuming it —
see `market/mfapi.py`'s docstring for the same pattern), unlike NSE/BSE's own endpoints
(Akamai-blocked from this sandbox, see `market/nse.py`).

This module only fetches and normalizes headlines. Sentiment scoring over the results is
a separate, deterministic concern — see `research/sentiment.py`.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from investment_agent.market.cache import CacheTTL, cache_get, cache_set

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)


def _parse_pub_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return None


async def get_news(query: str, limit: int = 15) -> list[dict[str, Any]]:
    """Recent news headlines matching `query`. Empty list (never raises) on any failure —
    callers degrade to DATA_UNAVAILABLE rather than failing the whole request."""
    query = query.strip()
    if not query:
        return []

    cache_key = f"news:google:{query.lower()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(GOOGLE_NEWS_RSS_URL, params=params)
    except httpx.HTTPError as exc:
        logger.info("Google News RSS failed for %r: %s", query, exc)
        return []
    if response.status_code >= 400:
        return []

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        logger.info("Google News RSS returned unparseable XML for %r", query)
        return []

    articles: list[dict[str, Any]] = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        source_el = item.find("source")
        articles.append(
            {
                "title": title,
                "link": (item.findtext("link") or "").strip() or None,
                "source_name": (source_el.text or "Google News").strip() if source_el is not None else "Google News",
                "published_at": _parse_pub_date(item.findtext("pubDate")),
            }
        )

    await cache_set(cache_key, json.dumps(articles), CacheTTL.NEWS)
    return articles
