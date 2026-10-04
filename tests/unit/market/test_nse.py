"""Tests for market/nse.py. See the module docstring there re: live-verification caveats —
these are respx-mocked against the documented response shape, not a live round trip."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from investment_agent.market import nse


@pytest.fixture(autouse=True)
def _reset_session():
    nse._invalidate_session()
    nse._blocked_until = None
    yield
    nse._invalidate_session()
    nse._blocked_until = None


def _patch_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(key: str) -> str | None:
        return None

    async def _fake_set(key: str, value: str, ttl_seconds: object) -> None:
        return None

    monkeypatch.setattr(nse, "cache_get", _fake_get)
    monkeypatch.setattr(nse, "cache_set", _fake_set)


@respx.mock
async def test_get_filings_parses_fixture_and_flags_risk_keywords(
    monkeypatch: pytest.MonkeyPatch, load_fixture: Callable[[str], Any]
):
    _patch_cache(monkeypatch)
    respx.get("https://www.nseindia.com/").mock(
        return_value=httpx.Response(200, headers={"set-cookie": "nsit=fake; Path=/"})
    )
    respx.get("https://www.nseindia.com/api/corporate-announcements").mock(
        return_value=httpx.Response(200, json=load_fixture("nse_announcements_tcs.json"))
    )

    filings = await nse.get_filings("TCS")

    assert len(filings) == 2
    assert filings[0]["subject"] == "Board Meeting Intimation for considering Q2 FY27 results"
    assert filings[0]["attachment_url"] == "https://www.nseindia.com/corporate/TCS_board_meeting.pdf"
    assert filings[1]["subject"] == "Resignation of Independent Director"


@respx.mock
async def test_get_filings_degrades_to_empty_list_on_block(monkeypatch: pytest.MonkeyPatch):
    """A 403 (Akamai or otherwise) must never raise — it must degrade to DATA_UNAVAILABLE."""
    _patch_cache(monkeypatch)
    respx.get("https://www.nseindia.com/").mock(return_value=httpx.Response(403))

    filings = await nse.get_filings("TCS")

    assert filings == []


@respx.mock
async def test_get_shareholding_parses_fixture_and_pledge_helper(
    monkeypatch: pytest.MonkeyPatch, load_fixture: Callable[[str], Any]
):
    _patch_cache(monkeypatch)
    respx.get("https://www.nseindia.com/").mock(
        return_value=httpx.Response(200, headers={"set-cookie": "nsit=fake; Path=/"})
    )
    respx.get("https://www.nseindia.com/api/corporate-shareholding-pattern").mock(
        return_value=httpx.Response(200, json=load_fixture("nse_shareholding_tcs.json"))
    )

    quarters = await nse.get_shareholding("TCS")

    assert len(quarters) == 2
    assert quarters[0]["promoter_pct"] == 72.3
    assert quarters[0]["promoter_pledge_pct"] == 0.0
    assert nse.latest_promoter_pledge_pct(quarters) == 0.0


def test_latest_promoter_pledge_pct_handles_empty_and_missing():
    assert nse.latest_promoter_pledge_pct([]) is None
    assert nse.latest_promoter_pledge_pct([{"promoter_pledge_pct": None}]) is None
