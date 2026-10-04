"""Read-only client for the INDstocks trading API (INDmoney).

Order placement is intentionally absent.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import httpx
import pyotp

from investment_agent.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

EQUITY_COLUMNS = (
    "EXCH",
    "SEGMENT",
    "SECURITY_ID",
    "INSTRUMENT_NAME",
    "EXPIRY_CODE",
    "TRADING_SYMBOL",
    "LOT_UNITS",
    "CUSTOM_SYMBOL",
    "EXPIRY_DATE",
    "STRIKE_PRICE",
    "OPTION_TYPE",
    "TICK_SIZE",
    "EXPIRY_FLAG",
    "SEM_EXCH_INSTRUMENT_TYPE",
    "SERIES",
    "SYMBOL_NAME",
)


class IndstocksError(RuntimeError):
    pass


_token_lock = asyncio.Lock()
_shared_token: str | None = None
_token_blocked_until: datetime | None = None


def token_cooldown_active() -> bool:
    return _token_blocked_until is not None and datetime.now(UTC) < _token_blocked_until


def _remember_token(token: str) -> str:
    global _shared_token
    _shared_token = token
    return token


def _forget_token() -> None:
    global _shared_token
    _shared_token = None


def scrip_code(exchange: str, security_id: str) -> str:
    return f"{exchange.strip().upper()}_{security_id.strip()}"


def parse_equity_instruments(csv_text: str) -> list[dict[str, str]]:
    """Parse the equity instruments master. Keeps NSE/BSE equity series EQ."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return []
    rows: list[dict[str, str]] = []
    for raw in reader:
        series = (raw.get("SERIES") or "").strip().upper()
        instrument = (raw.get("INSTRUMENT_NAME") or "").strip().upper()
        if series != "EQ" or instrument not in {"", "EQUITY"}:
            continue
        symbol = (raw.get("SYMBOL_NAME") or raw.get("TRADING_SYMBOL") or "").strip().upper()
        security_id = (raw.get("SECURITY_ID") or "").strip()
        exchange = (raw.get("EXCH") or "").strip().upper()
        if not symbol or not security_id or not exchange:
            continue
        rows.append(
            {
                "exchange": exchange,
                "segment": (raw.get("SEGMENT") or "E").strip(),
                "security_id": security_id,
                "trading_symbol": (raw.get("TRADING_SYMBOL") or symbol).strip().upper(),
                "symbol_name": symbol,
                "series": series,
                "instrument_name": instrument or "EQUITY",
            }
        )
    return rows


def parse_index_instruments(csv_text: str) -> list[dict[str, str]]:
    """Index file is three columns. The second column is the index name, not a segment."""
    reader = csv.reader(io.StringIO(csv_text))
    rows: list[dict[str, str]] = []
    header_seen = False
    for parts in reader:
        if not parts:
            continue
        if not header_seen:
            header_seen = True
            continue
        if len(parts) < 3:
            continue
        exchange, name, security_id = parts[0].strip().upper(), parts[1].strip(), parts[2].strip()
        if exchange and name and security_id:
            rows.append({"exchange": exchange, "name": name, "security_id": security_id})
    return rows


class IndstocksClient:
    def __init__(
        self, settings: Settings | None = None, http: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._http = http
        self._owns_http = http is None

    async def __aenter__(self) -> Self:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.settings.INDSTOCKS_BASE_URL, timeout=60.0)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise IndstocksError("HTTP client is not open")
        return self._http

    async def _mint_token(self) -> str:
        client_id = (self.settings.INDSTOCKS_CLIENT_ID or "").strip()
        mpin = (self.settings.INDSTOCKS_MPIN or "").strip()
        secret = (self.settings.INDSTOCKS_TOTP_SECRET or "").strip()
        if not (client_id and mpin and secret):
            raise IndstocksError(
                "INDstocks access token is missing or expired. "
                "Set INDSTOCKS_ACCESS_TOKEN or INDSTOCKS_CLIENT_ID, INDSTOCKS_MPIN, and INDSTOCKS_TOTP_SECRET."
            )
        if token_cooldown_active():
            raise IndstocksError(
                "INDstocks allows one login token per minute. Wait a minute, then press Sync."
            )
        async def post_token() -> httpx.Response:
            return await self._client().post(
                "/generate/token",
                headers={"x-api-key": client_id, "Content-Type": "application/json"},
                json={"mpin": mpin, "totp": pyotp.TOTP(secret).now()},
            )

        response = await post_token()
        if response.status_code >= 400:
            if response.status_code == 429:
                global _token_blocked_until
                _token_blocked_until = datetime.now(UTC) + timedelta(seconds=60)
                raise IndstocksError(
                    "INDstocks allows one login token per minute. Wait a minute, then press Sync."
                )
            raise IndstocksError(f"INDstocks token refresh failed ({response.status_code})")
        payload = response.json()
        token = ""
        if isinstance(payload, dict):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            token = str((data or {}).get("token") or payload.get("token") or "")
        if not token:
            raise IndstocksError("INDstocks token refresh returned no token")
        return _remember_token(token)

    async def _token(self, *, force_refresh: bool = False) -> str:
        async with _token_lock:
            if force_refresh:
                _forget_token()
            if _shared_token:
                return _shared_token
            env_token = (self.settings.INDSTOCKS_ACCESS_TOKEN or "").strip()
            if env_token and not force_refresh:
                return _remember_token(env_token)
            return await self._mint_token()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = token
        response = await self._client().request(method, path, headers=headers, **kwargs)
        if response.status_code == 401:
            token = await self._token(force_refresh=True)
            headers["Authorization"] = token
            response = await self._client().request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise IndstocksError(f"INDstocks {method} {path} failed ({response.status_code})")
        return response

    async def get_equity_instruments(self) -> list[dict[str, str]]:
        response = await self._request("GET", "/market/instruments", params={"source": "equity"})
        return parse_equity_instruments(response.text)

    async def get_index_instruments(self) -> list[dict[str, str]]:
        response = await self._request("GET", "/market/instruments", params={"source": "index"})
        return parse_index_instruments(response.text)

    async def get_quotes(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        if not codes:
            return {}
        response = await self._request(
            "GET",
            "/market/quotes/full",
            params={"scrip-codes": ",".join(codes)},
        )
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    async def get_ltp(self, codes: list[str]) -> dict[str, float]:
        if not codes:
            return {}
        response = await self._request(
            "GET",
            "/market/quotes/ltp",
            params={"scrip-codes": ",".join(codes)},
        )
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        prices: dict[str, float] = {}
        if isinstance(data, dict):
            for code, quote in data.items():
                if isinstance(quote, dict) and quote.get("live_price") is not None:
                    prices[code] = float(quote["live_price"])
        return prices

    async def get_candles(
        self,
        code: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """OHLCV candles for one instrument. Daily history is limited to one year per call."""
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        response = await self._request(
            "GET",
            f"/market/historical/{interval}",
            params={"scrip-codes": code, "start_time": start_ms, "end_time": end_ms},
        )
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        body = data.get(code) if isinstance(data, dict) else None
        candles = body.get("candles") if isinstance(body, dict) else None
        return candles if isinstance(candles, list) else []

    async def get_daily_bars(
        self,
        codes: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[dict[str, Any]]]:
        """Daily candles. The API accepts at most five scrip codes per call."""
        if not codes:
            return {}
        if len(codes) > 5:
            raise IndstocksError("Daily history accepts at most 5 scrip codes per call")
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        response = await self._request(
            "GET",
            "/market/historical/1day",
            params={"scrip-codes": ",".join(codes), "start_time": start_ms, "end_time": end_ms},
        )
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        bars: dict[str, list[dict[str, Any]]] = {}
        if not isinstance(data, dict):
            return bars
        for code, body in data.items():
            candles = body.get("candles") if isinstance(body, dict) else None
            if isinstance(candles, list):
                bars[code] = candles
        return bars

    async def get_holdings(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/portfolio/holdings")
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else []
        return data if isinstance(data, list) else []

    async def get_funds(self) -> dict[str, Any]:
        response = await self._request("GET", "/funds")
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}


def equity_cash_available(funds: dict[str, Any]) -> float:
    detailed = funds.get("detailed_avl_balance")
    if isinstance(detailed, dict) and detailed.get("eq_cnc") is not None:
        return float(detailed["eq_cnc"])
    if funds.get("withdrawal_balance") is not None:
        return float(funds["withdrawal_balance"])
    return 0.0


def quote_retrieved_at() -> datetime:
    return datetime.now(UTC)
