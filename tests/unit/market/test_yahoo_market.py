"""Worked example for the Gap 10 provider-test pattern: mocked HTTP + recorded fixture.

Covers quote_symbol end to end, including the crumb/cookie handshake (`_ensure_crumb`) and
the Gap 6 cache wiring, so this doubles as a regression test for both.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from investment_agent.market import yahoo_market


@pytest.fixture(autouse=True)
def _reset_crumb_cache():
    """The module caches the crumb/cookie at import scope; start each test from a clean slate."""
    yahoo_market._invalidate_crumb()
    yield
    yahoo_market._invalidate_crumb()


@pytest.mark.usefixtures("no_redis")
@respx.mock
async def test_quote_symbol_parses_recorded_fixture(load_fixture: Callable[[str], Any]):
    respx.get("https://fc.yahoo.com").mock(
        return_value=httpx.Response(404, headers={"set-cookie": "A3=fake-cookie-value; Path=/"})
    )
    respx.get("https://query1.finance.yahoo.com/v1/test/getcrumb").mock(
        return_value=httpx.Response(200, text="test-crumb")
    )
    respx.get("https://query1.finance.yahoo.com/v7/finance/quote").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo_quote_tcs.json"))
    )

    quote = await yahoo_market.quote_symbol("TCS", "NSE")

    assert quote is not None
    assert quote["symbol"] == "TCS"
    assert quote["name"] == "TATA CONSULTANCY SERV LT"
    assert quote["live_price"] == 2075.0
    assert quote["day_change_percentage"] == -0.26
    assert quote["pe_ratio"] == 15.08
    assert quote["exchange"] == "NSE"


@pytest.mark.usefixtures("no_redis")
@respx.mock
async def test_quote_symbol_returns_none_when_yahoo_has_no_match():
    respx.get("https://fc.yahoo.com").mock(
        return_value=httpx.Response(404, headers={"set-cookie": "A3=fake-cookie-value; Path=/"})
    )
    respx.get("https://query1.finance.yahoo.com/v1/test/getcrumb").mock(
        return_value=httpx.Response(200, text="test-crumb")
    )
    respx.get("https://query1.finance.yahoo.com/v7/finance/quote").mock(
        return_value=httpx.Response(200, json={"quoteResponse": {"result": [], "error": None}})
    )

    quote = await yahoo_market.quote_symbol("NOSUCHTICKER", "NSE")

    assert quote is None


@pytest.mark.usefixtures("no_redis")
@respx.mock
async def test_quote_symbol_retries_once_on_401_then_succeeds(load_fixture: Callable[[str], Any]):
    """Covers the Gap-related 401 retry added to _crumbed_request: a revoked crumb should
    not surface as a permanent failure, only as one retry with a freshly minted session."""
    respx.get("https://fc.yahoo.com").mock(
        return_value=httpx.Response(404, headers={"set-cookie": "A3=fake-cookie-value; Path=/"})
    )
    respx.get("https://query1.finance.yahoo.com/v1/test/getcrumb").mock(
        return_value=httpx.Response(200, text="test-crumb")
    )
    quote_route = respx.get("https://query1.finance.yahoo.com/v7/finance/quote")
    quote_route.side_effect = [
        httpx.Response(401),
        httpx.Response(200, json=load_fixture("yahoo_quote_tcs.json")),
    ]

    quote = await yahoo_market.quote_symbol("TCS", "NSE")

    assert quote is not None
    assert quote["symbol"] == "TCS"
    assert quote_route.call_count == 2
