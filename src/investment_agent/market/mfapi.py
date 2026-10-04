"""mfapi.in — free, keyless full NAV history and scheme search for Indian mutual funds.

Verified live from this environment (unlike market/nse.py's endpoints, which were blocked
here): `GET /mf/search?q=` and `GET /mf/{scheme_code}` both return real data. The response
shapes below (meta.fund_house/scheme_category/isin_growth, data[].date in dd-mm-yyyy, nav
as a numeric string, newest-first) were captured from a live call, not reconstructed from
docs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from investment_agent.config.settings import get_settings
from investment_agent.market.amfi import category_index, classify_sebi_group, fetch_nav_file
from investment_agent.market.cache import CacheTTL, cache_get, cache_set

logger = logging.getLogger(__name__)

MFAPI_BASE = "https://api.mfapi.in"
_RETRY_DELAYS = (0.5, 1.5)  # seconds; 1 initial attempt + len(_RETRY_DELAYS) retries


async def _get_with_retry(url: str, params: dict[str, Any] | None = None) -> httpx.Response | None:
    """GET with a short retry/backoff. Returns None (never raises) if every attempt fails —
    callers degrade to DATA_UNAVAILABLE rather than propagating a transient network error."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt, delay in enumerate((0.0, *_RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await client.get(url, params=params)
                if response.status_code < 500:
                    return response
                logger.info("mfapi.in %s returned %s (attempt %s)", url, response.status_code, attempt + 1)
            except httpx.HTTPError as exc:
                logger.info("mfapi.in %s failed: %s (attempt %s)", url, exc, attempt + 1)
    return None


def _parse_nav_date(raw: str) -> str:
    """mfapi.in dates are dd-mm-yyyy; normalize to ISO (yyyy-mm-dd) for the rest of the app."""
    return datetime.strptime(raw, "%d-%m-%Y").replace(tzinfo=UTC).date().isoformat()


async def search(query: str) -> list[dict[str, Any]]:
    """Scheme name/code search. Empty list (not an error) on any failure or no match."""
    query = query.strip()
    if not query:
        return []
    cache_key = f"mfapi:search:{query.lower()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    response = await _get_with_retry(f"{MFAPI_BASE}/mf/search", params={"q": query})
    if response is None or response.status_code >= 400:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    results = [
        {"scheme_code": str(item.get("schemeCode")), "scheme_name": item.get("schemeName")}
        for item in payload
        if item.get("schemeCode") is not None
    ]
    await cache_set(cache_key, json.dumps(results), CacheTTL.MF_SEARCH)
    return results


def fund_house_name(scheme_name: str) -> str:
    """AMC name is the text before 'Fund' in the scheme title."""
    for marker in (" Fund", " FUND"):
        index = scheme_name.find(marker)
        if index > 2:
            return scheme_name[:index].strip(" -")
    return scheme_name.split("-", 1)[0].strip()


_CATEGORY_LABELS = {
    "large": "Large cap",
    "large_mid": "Large & mid",
    "mid": "Mid cap",
    "small": "Small cap",
    "flexi": "Flexi cap",
    "equity": "Equity",
    "debt": "Debt",
    "index": "Index",
    "elss": "ELSS",
    "hybrid": "Hybrid",
    "gold": "Gold",
    "solution": "Solution",
    "other": "Other",
}

CATEGORY_ORDER = [
    "Large cap",
    "Large & mid",
    "Mid cap",
    "Small cap",
    "Flexi cap",
    "Equity",
    "Index",
    "ELSS",
    "Hybrid",
    "Gold",
    "Debt",
    "Solution",
    "Other",
]


def scheme_category_label(scheme_name: str, category: str | None = None) -> str:
    return _CATEGORY_LABELS.get(classify_sebi_group(category, scheme_name), "Other")


async def _amfi_category_index() -> dict[str, str]:
    """Official AMFI category header for each live scheme code. Empty if the file is down."""
    cache_key = "amfi:category-index:v1"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)
    try:
        text = await fetch_nav_file(get_settings().AMFI_NAV_URL)
    except httpx.HTTPError as exc:
        logger.info("AMFI category index failed: %s", exc)
        return {}
    index = category_index(text)
    if index:
        await cache_set(cache_key, json.dumps(index), CacheTTL.MF_CATALOGUE)
    return index


async def list_schemes() -> list[dict[str, str]]:
    """Full scheme catalogue from https://api.mfapi.in/mf. Cached 15 minutes."""
    cache_key = "mfapi:catalogue:v4"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.get(f"{MFAPI_BASE}/mf")
    except httpx.HTTPError as exc:
        logger.info("mfapi.in catalogue failed: %s", exc)
        return []
    if response.status_code >= 400:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    amfi_index = await _amfi_category_index()
    schemes = []
    for item in payload:
        code = item.get("schemeCode")
        name = item.get("schemeName")
        if code is None or not name:
            continue
        header = amfi_index.get(str(code), "")
        schemes.append(
            {
                "scheme_code": str(code),
                "scheme_name": str(name),
                "fund_house": fund_house_name(str(name)),
                "amfi_category": header,
                "category": scheme_category_label(str(name), header or None),
            }
        )
    await cache_set(cache_key, json.dumps(schemes), CacheTTL.MF_CATALOGUE)
    return schemes


async def fetch_nav_history(scheme_code: str) -> dict[str, Any] | None:
    """Full NAV history (newest first) plus scheme metadata. None on any failure.

    `nav_history` entries are `{"date": "YYYY-MM-DD", "nav": float}`, oldest-last (matching
    mfapi.in's own ordering) — `portfolio/fund_metrics.py` depends on that ordering.
    """
    scheme_code = scheme_code.strip()
    cache_key = f"mfapi:history:{scheme_code}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    response = await _get_with_retry(f"{MFAPI_BASE}/mf/{scheme_code}")
    if response is None or response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    meta = payload.get("meta") or {}
    raw_data = payload.get("data") or []

    nav_history: list[dict[str, Any]] = []
    for entry in raw_data:
        try:
            nav_history.append({"date": _parse_nav_date(entry["date"]), "nav": float(entry["nav"])})
        except (KeyError, ValueError, TypeError):
            continue

    result = {
        "scheme_code": str(meta.get("scheme_code") or scheme_code),
        "scheme_name": meta.get("scheme_name"),
        "fund_house": meta.get("fund_house"),
        "scheme_category": meta.get("scheme_category"),
        "isin_growth": meta.get("isin_growth"),
        "nav_history": nav_history,
        "source_name": "mfapi.in",
        "source_url": f"{MFAPI_BASE}/mf/{scheme_code}",
        "data_date": nav_history[0]["date"] if nav_history else None,
    }
    await cache_set(cache_key, json.dumps(result), CacheTTL.MF_NAV_HISTORY)
    return result
