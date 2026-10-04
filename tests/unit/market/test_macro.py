"""Tests for market/macro.py. Fixtures mirror FRED's real `fredgraph.csv` shape (confirmed
live-reachable from this environment, see macro.py's docstring), including a `.`
missing-value row, which is how FRED marks a gap in the series."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from investment_agent.market import macro

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get(key: str) -> str | None:
        return None

    async def _fake_set(key: str, value: str, ttl_seconds: object) -> None:
        return None

    monkeypatch.setattr(macro, "cache_get", _fake_get)
    monkeypatch.setattr(macro, "cache_set", _fake_set)


@respx.mock
async def test_usd_inr_rate_parses_fixture_and_takes_latest():
    csv_body = (FIXTURES_DIR / "fred_dexinus.csv").read_text(encoding="utf-8")
    respx.get(macro.FRED_CSV_URL).mock(return_value=httpx.Response(200, text=csv_body))

    result = await macro.usd_inr_rate()

    assert result is not None
    assert result["value"] == 95.81
    assert result["data_date"] == "2026-09-25"


@respx.mock
async def test_usd_inr_rate_returns_none_on_server_error():
    respx.get(macro.FRED_CSV_URL).mock(return_value=httpx.Response(500))
    assert await macro.usd_inr_rate() is None


@respx.mock
async def test_cpi_inflation_yoy_skips_missing_value_row_and_takes_latest():
    csv_body = (FIXTURES_DIR / "fred_cpi_india.csv").read_text(encoding="utf-8")
    respx.get(macro.FRED_CSV_URL).mock(return_value=httpx.Response(200, text=csv_body))

    result = await macro.cpi_inflation_yoy()

    assert result is not None
    # Latest non-missing row is 2025-03-01, not the "." row for 2025-02-01.
    assert result["value_pct"] == 2.95
    assert result["data_date"] == "2025-03-01"


@respx.mock
async def test_cpi_inflation_yoy_returns_none_when_every_row_is_missing():
    respx.get(macro.FRED_CSV_URL).mock(
        return_value=httpx.Response(200, text="observation_date,CPALTT01INM659N\n2025-01-01,.\n")
    )
    assert await macro.cpi_inflation_yoy() is None


@respx.mock
async def test_get_macro_snapshot_degrades_each_field_independently(monkeypatch: pytest.MonkeyPatch):
    async def fake_usd_inr_rate():
        return {"value": 95.81, "data_date": "2026-09-25", "source_name": "x", "source_url": "y"}

    async def fake_cpi_inflation_yoy():
        return None

    monkeypatch.setattr(macro, "usd_inr_rate", fake_usd_inr_rate)
    monkeypatch.setattr(macro, "cpi_inflation_yoy", fake_cpi_inflation_yoy)

    snapshot = await macro.get_macro_snapshot()

    assert snapshot["usd_inr"]["status"] == "OK"
    assert snapshot["usd_inr"]["value"] == 95.81
    assert snapshot["cpi_inflation_yoy"] == {"status": "DATA_UNAVAILABLE"}
