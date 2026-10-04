"""Tests for market/mfapi.py. Fixtures were recorded from a real live call during
development (confirmed reachable from this environment, unlike NSE/BSE — see
market/nse.py's docstring) and trimmed to a handful of entries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from investment_agent.market import mfapi


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get(key: str) -> str | None:
        return None

    async def _fake_set(key: str, value: str, ttl_seconds: object) -> None:
        return None

    monkeypatch.setattr(mfapi, "cache_get", _fake_get)
    monkeypatch.setattr(mfapi, "cache_set", _fake_set)


@respx.mock
async def test_search_parses_recorded_fixture(load_fixture: Callable[[str], Any]):
    respx.get("https://api.mfapi.in/mf/search").mock(
        return_value=httpx.Response(200, json=load_fixture("mfapi_search_hdfc.json"))
    )

    results = await mfapi.search("hdfc flexi")

    assert len(results) == 5
    assert results[0] == {"scheme_code": "117991", "scheme_name": "HDFC FMP 371D October 2012 (1)-Flexi Option"}


@respx.mock
async def test_search_empty_query_short_circuits_without_a_request():
    # No respx route registered at all — if this made a request, respx would raise.
    assert await mfapi.search("   ") == []


@respx.mock
async def test_search_degrades_to_empty_list_on_server_error():
    respx.get("https://api.mfapi.in/mf/search").mock(return_value=httpx.Response(500))
    assert await mfapi.search("hdfc") == []


@respx.mock
async def test_fetch_nav_history_parses_recorded_fixture_and_normalizes_dates(
    load_fixture: Callable[[str], Any]
):
    respx.get("https://api.mfapi.in/mf/119598").mock(
        return_value=httpx.Response(200, json=load_fixture("mfapi_scheme_119598.json"))
    )

    result = await mfapi.fetch_nav_history("119598")

    assert result is not None
    assert result["scheme_code"] == "119598"
    assert result["fund_house"] == "SBI Mutual Fund"
    assert result["scheme_category"] == "Equity Scheme - Large Cap Fund"
    assert result["source_name"] == "mfapi.in"
    # mfapi.in dates are dd-mm-yyyy; normalized to ISO for the rest of the app.
    assert result["nav_history"][0]["date"] == "2026-10-01"
    assert result["nav_history"][0]["nav"] == 98.9141
    assert result["data_date"] == "2026-10-01"


@respx.mock
async def test_fetch_nav_history_returns_none_on_failure():
    respx.get("https://api.mfapi.in/mf/000000").mock(return_value=httpx.Response(404))
    assert await mfapi.fetch_nav_history("000000") is None
