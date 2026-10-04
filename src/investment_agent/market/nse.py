"""Corporate announcements and shareholding pattern from NSE's public (keyless) JSON API.

NSE sits behind Akamai bot protection, the same shape of problem Yahoo's crumb/cookie dance
solves: warm up a session against the homepage to collect cookies, then reuse that session
for the API calls below. Unlike Yahoo there is no `crumb` query param — the cookies alone
authorize the request.

**Verification note:** these endpoints could not be exercised against the live API while
writing this module — the sandbox this was written in is itself blocked by Akamai (403 on
the plain homepage GET, before any API call), so correctness here rests on matching NSE's
documented/widely-used public endpoint shapes and on the respx-mocked tests in
tests/unit/market/test_nse.py, not on a live round trip. Verify against a real NSE response
once this runs somewhere with unblocked egress, and adjust field names if NSE's response
shape has drifted.

Every function here degrades to an empty list instead of raising — a blocked or
rate-limited NSE must never take down the research graph (see Gap 1 wiring in
graph/nodes.py), it should just leave that candidate's filings as DATA_UNAVAILABLE.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from investment_agent.market.cache import CacheTTL, cache_get, cache_set

logger = logging.getLogger(__name__)

NSE = "https://www.nseindia.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_cookie: str | None = None
_cookie_at: datetime | None = None
_session_lock = asyncio.Lock()

# If a warm-up attempt fails (403/timeout), stop retrying for a cooldown window instead of
# re-attempting — and paying its latency — for every candidate in the same graph run. A
# research run can touch 20-30 candidates via asyncio.gather; without this, each one would
# serialize through _session_lock and independently retry a doomed request.
_blocked_until: datetime | None = None
_BLOCK_COOLDOWN = timedelta(seconds=90)

# Short, split connect/read timeouts: this is best-effort enrichment data, not a request a
# user is blocking on, so a slow/blackholed connection must fail fast rather than eat the
# httpx default per attempt.
_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)


class NseError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{NSE}/",
    }
    if _cookie:
        headers["Cookie"] = _cookie
    return headers


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, headers=_headers())


def _invalidate_session() -> None:
    global _cookie, _cookie_at
    _cookie = None
    _cookie_at = None


async def _ensure_session(http: httpx.AsyncClient, *, force_refresh: bool = False) -> None:
    global _cookie, _cookie_at, _blocked_until
    async with _session_lock:
        if (
            not force_refresh
            and _cookie
            and _cookie_at
            and datetime.now(UTC) - _cookie_at < timedelta(minutes=10)
        ):
            http.headers["Cookie"] = _cookie
            return
        if _blocked_until and datetime.now(UTC) < _blocked_until:
            raise NseError("NSE warm-up is in cooldown after a recent failure")
        try:
            home = await http.get(f"{NSE}/")
        except httpx.HTTPError as exc:
            _blocked_until = datetime.now(UTC) + _BLOCK_COOLDOWN
            raise NseError(f"NSE session warm-up failed ({exc})") from exc
        if home.status_code >= 400:
            _blocked_until = datetime.now(UTC) + _BLOCK_COOLDOWN
            raise NseError(f"NSE session warm-up failed ({home.status_code})")
        _blocked_until = None
        set_cookie = home.headers.get("set-cookie") or ""
        _cookie = set_cookie
        _cookie_at = datetime.now(UTC)
        http.headers["Cookie"] = _cookie


async def _session_get(http: httpx.AsyncClient, path: str, params: dict[str, Any]) -> httpx.Response:
    """GET an NSE API path, retrying once with a fresh session on 401/403 (session revoked)."""
    await _ensure_session(http)
    response = await http.get(f"{NSE}{path}", params=params)
    if response.status_code in (401, 403):
        _invalidate_session()
        await _ensure_session(http, force_refresh=True)
        response = await http.get(f"{NSE}{path}", params=params)
    return response


def _normalize_announcement(row: dict[str, Any]) -> dict[str, Any]:
    attachment = row.get("attchmntFile") or row.get("attachmentFile") or ""
    return {
        "symbol": row.get("symbol"),
        "subject": row.get("desc") or row.get("subject") or row.get("attchmntText") or "",
        "category": row.get("csub_category") or row.get("category") or "General",
        "announced_at": row.get("an_dt") or row.get("sort_date") or row.get("attchmntDate"),
        "attachment_url": f"{NSE}{attachment}" if attachment.startswith("/") else attachment or None,
        "source_name": "NSE Corporate Announcements",
        "source_url": f"{NSE}/companies-listing/corporate-filings-announcements",
    }


async def get_filings(symbol: str) -> list[dict[str, Any]]:
    """Latest corporate announcements (results, board meetings, dividends, splits, etc.)."""
    symbol = symbol.upper().strip()
    cache_key = f"nse:filings:{symbol}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    try:
        async with await _client() as http:
            response = await _session_get(
                http,
                "/api/corporate-announcements",
                {"index": "equities", "symbol": symbol},
            )
        if response.status_code >= 400:
            logger.info("NSE filings unavailable for %s (%s)", symbol, response.status_code)
            return []
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data") or []
        filings = [_normalize_announcement(row) for row in rows if isinstance(row, dict)]
    except Exception as exc:
        logger.info("NSE filings fetch failed for %s: %s", symbol, exc)
        return []

    await cache_set(cache_key, json.dumps(filings), CacheTTL.FILINGS)
    return filings


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    """First non-None value for any of `keys` — unlike `a or b`, a legitimate 0.0 (e.g. no
    promoter pledge) is not falsy-skipped in favor of a later, absent key."""
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _normalize_shareholding_quarter(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "period_end": _first_present(row, "date", "to_date", "period"),
        "promoter_pct": _first_present(row, "promoter", "promoter_group_pct"),
        "promoter_pledge_pct": _first_present(row, "pledge", "promoter_pledge_pct"),
        "fii_pct": _first_present(row, "fii", "fii_pct"),
        "dii_pct": _first_present(row, "dii", "dii_pct"),
        "public_pct": _first_present(row, "public", "public_pct"),
    }


async def get_shareholding(symbol: str) -> list[dict[str, Any]]:
    """Quarter-wise promoter/FII/DII/public holding and promoter pledge, newest first.

    Lower confidence than `get_filings` — see the module docstring's verification note.
    """
    symbol = symbol.upper().strip()
    cache_key = f"nse:shareholding:{symbol}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    try:
        async with await _client() as http:
            response = await _session_get(
                http,
                "/api/corporate-shareholding-pattern",
                {"index": "equities", "symbol": symbol},
            )
        if response.status_code >= 400:
            logger.info("NSE shareholding unavailable for %s (%s)", symbol, response.status_code)
            return []
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data") or []
        quarters = [_normalize_shareholding_quarter(row) for row in rows if isinstance(row, dict)]
    except Exception as exc:
        logger.info("NSE shareholding fetch failed for %s: %s", symbol, exc)
        return []

    await cache_set(cache_key, json.dumps(quarters), CacheTTL.FILINGS)
    return quarters


def latest_promoter_pledge_pct(shareholding: list[dict[str, Any]]) -> float | None:
    """Most recent quarter's promoter pledge percentage, or None if unavailable."""
    if not shareholding:
        return None
    value = shareholding[0].get("promoter_pledge_pct")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
