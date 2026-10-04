"""Live NSE quotes from the same Yahoo Finance endpoints used by the Indian Stock Market API.

That project (https://github.com/0xramm/Indian-Stock-Market-API) does not publish history
or a movers feed. Quotes use its batch endpoint, and charts use Yahoo's public chart API.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

YAHOO = "https://query1.finance.yahoo.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_crumb: str | None = None
_cookie: str | None = None
_crumb_at: datetime | None = None
_crumb_lock = asyncio.Lock()

CHART_RANGES = {
    "1d": ("5m", "1d"),
    "1w": ("15m", "5d"),
    "1m": ("1d", "1mo"),
    "3m": ("1d", "3mo"),
    "6m": ("1d", "6mo"),
    "1y": ("1d", "1y"),
    "5y": ("1d", "5y"),
}


class MarketDataError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if _cookie:
        headers["Cookie"] = _cookie
    return headers


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=_headers())


def _invalidate_crumb() -> None:
    """Drop the cached crumb/cookie so the next call mints a fresh session.

    Yahoo can revoke a crumb before its soft 30-minute TTL (anomaly detection,
    load balancer rotation, etc). Call sites retry once after invalidating
    instead of trusting the cache blindly.
    """
    global _crumb, _cookie, _crumb_at
    _crumb = None
    _cookie = None
    _crumb_at = None


async def _ensure_crumb(http: httpx.AsyncClient, *, force_refresh: bool = False) -> str:
    global _crumb, _cookie, _crumb_at
    async with _crumb_lock:
        if (
            not force_refresh
            and _crumb
            and _crumb_at
            and datetime.now(UTC) - _crumb_at < timedelta(minutes=30)
        ):
            http.headers["Cookie"] = _cookie or ""
            return _crumb
        home = await http.get("https://fc.yahoo.com")
        set_cookie = home.headers.get("set-cookie") or ""
        _cookie = set_cookie.split(";", 1)[0]
        http.headers["Cookie"] = _cookie
        crumb_response = await http.get(f"{YAHOO}/v1/test/getcrumb")
        crumb = crumb_response.text.strip()
        if crumb_response.status_code >= 400 or not crumb or crumb.startswith("{"):
            raise MarketDataError("Yahoo Finance did not return a quote session")
        _crumb = crumb
        _crumb_at = datetime.now(UTC)
        return crumb


def _symbol(raw: str) -> str:
    return raw.upper().removesuffix(".NS").removesuffix(".BO")


def ticker_for(symbol: str, exchange: str = "NSE") -> str:
    raw = symbol.upper().strip()
    if raw.endswith((".NS", ".BO")):
        return raw
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{_symbol(raw)}{suffix}"


def _quote_from_yahoo(quote: dict[str, Any]) -> dict[str, Any] | None:
    price = quote.get("regularMarketPrice")
    if price is None:
        return None
    symbol = _symbol(str(quote.get("symbol") or ""))
    change_pct = quote.get("regularMarketChangePercent")
    return {
        "symbol": symbol,
        "name": quote.get("shortName") or quote.get("longName") or symbol,
        "live_price": float(price),
        "day_change": float(quote.get("regularMarketChange") or 0),
        "day_change_percentage": float(change_pct or 0),
        "day_open": quote.get("regularMarketOpen"),
        "day_high": quote.get("regularMarketDayHigh"),
        "day_low": quote.get("regularMarketDayLow"),
        "prev_close": quote.get("regularMarketPreviousClose"),
        "volume": float(quote.get("regularMarketVolume") or 0),
        "pe_ratio": quote.get("trailingPE"),
        "market_cap_cr": (
            round(float(quote["marketCap"]) / 1e7, 2) if quote.get("marketCap") else None
        ),
        "exchange": "BSE" if str(quote.get("symbol") or "").endswith(".BO") or quote.get("exchange") == "BSE" else "NSE",
    }


async def _crumbed_request(
    http: httpx.AsyncClient,
    make_request: Callable[[str], Any],
) -> httpx.Response:
    """Issue a crumb-authenticated request, retrying once with a fresh session on 401.

    Yahoo occasionally revokes a crumb/cookie pair before the soft TTL expires;
    without this retry every subsequent call fails until the process restarts.
    """
    crumb = await _ensure_crumb(http)
    response = await make_request(crumb)
    if response.status_code == 401:
        _invalidate_crumb()
        crumb = await _ensure_crumb(http, force_refresh=True)
        response = await make_request(crumb)
    return response


async def screen_movers(offset: int, limit: int, exchange: str = "NSE") -> tuple[list[dict[str, Any]], int]:
    """Equities on NSE or BSE with the largest session move, paged."""
    venue = "BSE" if exchange.upper() == "BSE" else "NSI"
    body = {
        "size": limit,
        "offset": offset,
        "sortField": "percentchange",
        "sortType": "DESC",
        "quoteType": "EQUITY",
        "query": {
            "operator": "AND",
            "operands": [
                {"operator": "EQ", "operands": ["region", "in"]},
                {"operator": "EQ", "operands": ["exchange", venue]},
                {"operator": "GT", "operands": ["intradaymarketcap", 20_000_000_000]},
            ],
        },
    }
    async with await _client() as http:
        response = await _crumbed_request(
            http,
            lambda crumb: http.post(f"{YAHOO}/v1/finance/screener", params={"crumb": crumb}, json=body),
        )
    if response.status_code >= 400:
        raise MarketDataError(f"Market screener failed ({response.status_code})")
    result = (response.json().get("finance") or {}).get("result") or []
    if not result:
        return [], 0
    page = result[0]
    rows = []
    for quote in page.get("quotes") or []:
        row = _quote_from_yahoo(quote)
        if row is not None:
            rows.append(row)
    return rows, int(page.get("total") or 0)


async def quote_symbol(symbol: str, exchange: str = "NSE") -> dict[str, Any] | None:
    ticker = ticker_for(symbol, exchange)
    async with await _client() as http:
        response = await _crumbed_request(
            http,
            lambda crumb: http.get(f"{YAHOO}/v7/finance/quote", params={"symbols": ticker, "crumb": crumb}),
        )
    if response.status_code >= 400:
        raise MarketDataError(f"Quote failed ({response.status_code})")
    result = ((response.json().get("quoteResponse") or {}).get("result")) or []
    if not result:
        return None
    row = _quote_from_yahoo(result[0])
    if row is None:
        return None
    row["as_of"] = datetime.now(UTC).isoformat()
    return row


async def chart_symbol(symbol: str, range_key: str, exchange: str = "NSE") -> dict[str, Any] | None:
    spec = CHART_RANGES.get(range_key)
    if spec is None:
        raise ValueError(f"Unsupported range {range_key}")
    interval, yahoo_range = spec
    ticker = ticker_for(symbol, exchange)
    async with await _client() as http:
        response = await http.get(
            f"{YAHOO}/v8/finance/chart/{ticker}",
            params={"interval": interval, "range": yahoo_range},
        )
    if response.status_code >= 400:
        raise MarketDataError(f"Chart failed ({response.status_code})")
    result = ((response.json().get("chart") or {}).get("result")) or []
    if not result:
        return None
    timestamps = result[0].get("timestamp") or []
    closes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0]
    candles = []
    for index, ts in enumerate(timestamps):
        close = (closes.get("close") or [None])[index] if index < len(closes.get("close") or []) else None
        if close is None:
            continue
        candles.append(
            {
                "ts": int(ts),
                "open": (closes.get("open") or [None])[index],
                "high": (closes.get("high") or [None])[index],
                "low": (closes.get("low") or [None])[index],
                "close": float(close),
                "volume": (closes.get("volume") or [None])[index],
            }
        )
    return {"symbol": _symbol(symbol), "range": range_key, "interval": interval, "candles": candles}


def _raw(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("raw")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Any) -> float | None:
    number = _raw(value)
    if number is None:
        return None
    return round(number * 100, 2)


async def company_fundamentals(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    """ROE, debt, margins, and growth from Yahoo's free company profile."""
    ticker = ticker_for(symbol, exchange)
    modules = "financialData,defaultKeyStatistics,assetProfile"
    async with await _client() as http:
        response = await _crumbed_request(
            http,
            lambda crumb: http.get(
                f"{YAHOO}/v10/finance/quoteSummary/{ticker}",
                params={"modules": modules, "crumb": crumb},
            ),
        )
    if response.status_code >= 400:
        raise MarketDataError(f"Fundamentals failed ({response.status_code})")
    result = ((response.json().get("quoteSummary") or {}).get("result")) or []
    if not result:
        return {}
    profile = result[0]
    financials = profile.get("financialData") or {}
    stats = profile.get("defaultKeyStatistics") or {}
    about = profile.get("assetProfile") or {}
    debt_pct = _raw(financials.get("debtToEquity"))
    return {
        "sector": about.get("sector"),
        "industry": about.get("industry"),
        "roe_pct": _pct(financials.get("returnOnEquity")),
        "roa_pct": _pct(financials.get("returnOnAssets")),
        "debt_to_equity": round(debt_pct / 100, 2) if debt_pct is not None else None,
        "revenue_growth_pct": _pct(financials.get("revenueGrowth")),
        "earnings_growth_pct": _pct(financials.get("earningsGrowth")),
        "profit_margin_pct": _pct(financials.get("profitMargins")),
        "operating_margin_pct": _pct(financials.get("operatingMargins")),
        "eps": _raw(stats.get("trailingEps")),
        "book_value": _raw(stats.get("bookValue")),
        "source": "Yahoo Finance company profile",
    }


async def index_quotes() -> list[dict[str, Any]]:
    """Large, mid, small, sector indices and liquid ETFs."""
    catalog = {
        "^NSEI": ("Nifty 50", "Large cap"),
        "^BSESN": ("Sensex", "Large cap"),
        "^NSEBANK": ("Nifty Bank", "Sector"),
        "^CNXIT": ("Nifty IT", "Sector"),
        "^NSEMDCP50": ("Nifty Midcap", "Mid cap"),
        "NIFTYBEES.NS": ("Nifty BeES", "ETF"),
        "BANKBEES.NS": ("Bank BeES", "ETF"),
        "JUNIORBEES.NS": ("Junior BeES", "ETF"),
        "GOLDBEES.NS": ("Gold BeES", "ETF"),
        "ITBEES.NS": ("IT BeES", "ETF"),
    }
    async with await _client() as http:
        response = await _crumbed_request(
            http,
            lambda crumb: http.get(f"{YAHOO}/v7/finance/quote", params={"symbols": ",".join(catalog), "crumb": crumb}),
        )
    if response.status_code >= 400:
        raise MarketDataError(f"Index quote failed ({response.status_code})")
    result = ((response.json().get("quoteResponse") or {}).get("result")) or []
    items = []
    for quote in result:
        price = quote.get("regularMarketPrice")
        symbol = quote.get("symbol")
        if price is None or symbol not in catalog:
            continue
        name, bucket = catalog[symbol]
        items.append(
            {
                "symbol": _symbol(symbol) if not symbol.startswith("^") else symbol,
                "name": name,
                "bucket": bucket,
                "live_price": float(price),
                "day_change_percentage": float(quote.get("regularMarketChangePercent") or 0),
            }
        )
    return items


async def search_symbols(query: str, exchange: str = "NSE") -> list[dict[str, Any]]:
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    async with await _client() as http:
        response = await http.get(
            f"{YAHOO}/v1/finance/search",
            params={"q": query, "quotesCount": 20},
        )
    if response.status_code >= 400:
        raise MarketDataError(f"Search failed ({response.status_code})")
    matches = []
    for quote in (response.json().get("quotes") or []):
        symbol = str(quote.get("symbol") or "")
        if not symbol.endswith(suffix):
            continue
        matches.append(
            {
                "symbol": _symbol(symbol),
                "name": quote.get("shortname") or quote.get("longname") or _symbol(symbol),
                "exchange": "BSE" if suffix == ".BO" else "NSE",
            }
        )
    return matches
