"""Wiring tests for api/routes/funds.py (Workstream B, B3). DB access and mfapi.in calls
are monkeypatched — route functions are called directly (FastAPI route handlers are plain
async functions), matching the project's established pattern for testing route/assembly
code (see test_stock_score.py)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from investment_agent.api.routes import funds
from investment_agent.db.models.market import MutualFundScheme


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, scalars_rows=None, scalar_row=None, raise_on_scalars=False):
        self._scalars_rows = scalars_rows or []
        self._scalar_row = scalar_row
        self._raise_on_scalars = raise_on_scalars

    async def scalars(self, stmt):
        if self._raise_on_scalars:
            raise RuntimeError("database unavailable")
        return _FakeScalarsResult(self._scalars_rows)

    async def scalar(self, stmt):
        return self._scalar_row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession):
        self._session = session

    def __call__(self):
        return self._session


def _make_scheme(**overrides) -> MutualFundScheme:
    defaults = {
        "scheme_code": "119598",
        "name": "SBI Bluechip Fund - Direct Plan - Growth",
        "isin": None,
        "fund_house": "SBI Mutual Fund",
        "category": "Equity Scheme - Large Cap Fund",
        "sebi_group": "equity",
        "plan": "direct",
        "option": "growth",
        "latest_nav": 98.9141,
        "nav_date": date(2026, 10, 1),
    }
    defaults.update(overrides)
    return MutualFundScheme(**defaults)


# --- GET /funds/search ---------------------------------------------------------------


async def test_funds_search_uses_database_when_rows_found(monkeypatch: pytest.MonkeyPatch):
    scheme = _make_scheme()
    monkeypatch.setattr(funds, "async_session_factory", _FakeSessionFactory(_FakeSession(scalars_rows=[scheme])))

    result = await funds.funds_search(q="sbi bluechip", limit=20)

    assert result["source"] == "database"
    assert result["items"] == [funds._scheme_summary(scheme)]


async def test_funds_search_falls_back_to_mfapi_when_db_has_no_match(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(funds, "async_session_factory", _FakeSessionFactory(_FakeSession(scalars_rows=[])))

    async def fake_mfapi_search(query: str):
        return [{"scheme_code": "117991", "scheme_name": "HDFC FMP 371D"}]

    monkeypatch.setattr(funds, "mfapi_search", fake_mfapi_search)

    result = await funds.funds_search(q="hdfc", limit=20)

    assert result["source"] == "mfapi.in"
    assert result["items"] == [{"scheme_code": "117991", "scheme_name": "HDFC FMP 371D"}]


async def test_funds_search_raises_503_when_database_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(funds, "async_session_factory", _FakeSessionFactory(_FakeSession(raise_on_scalars=True)))

    with pytest.raises(HTTPException) as exc_info:
        await funds.funds_search(q="sbi", limit=20)

    assert exc_info.value.status_code == 503


# --- GET /funds/{scheme_code} ---------------------------------------------------------


_NAV_HISTORY_NEWEST_FIRST = [
    {"date": "2026-01-01", "nav": 150.0},
    {"date": "2025-07-01", "nav": 130.0},
    {"date": "2025-01-01", "nav": 120.0},
    {"date": "2024-01-01", "nav": 100.0},
]


async def test_fund_detail_returns_data_unavailable_when_history_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(funds, "async_session_factory", _FakeSessionFactory(_FakeSession()))

    async def fake_fetch_nav_history(scheme_code: str):
        return None

    monkeypatch.setattr(funds, "fetch_nav_history", fake_fetch_nav_history)

    result = await funds.fund_detail("000000")

    assert result["status"] == "DATA_UNAVAILABLE"
    assert result["facts"] is None


async def test_fund_detail_ok_uses_db_facts_and_computes_returns_and_risk(monkeypatch: pytest.MonkeyPatch):
    scheme = _make_scheme()
    monkeypatch.setattr(funds, "async_session_factory", _FakeSessionFactory(_FakeSession(scalar_row=scheme)))

    async def fake_fetch_nav_history(scheme_code: str):
        return {
            "scheme_code": "119598",
            "scheme_name": "SBI Bluechip Fund",
            "fund_house": "SBI Mutual Fund",
            "scheme_category": "Equity Scheme - Large Cap Fund",
            "nav_history": _NAV_HISTORY_NEWEST_FIRST,
            "source_name": "mfapi.in",
            "source_url": "https://api.mfapi.in/mf/119598",
            "data_date": "2026-01-01",
        }

    monkeypatch.setattr(funds, "fetch_nav_history", fake_fetch_nav_history)

    result = await funds.fund_detail("119598")

    assert result["status"] == "OK"
    assert result["facts"] == funds._scheme_summary(scheme)
    # 2 years from 100.0 (2024-01-01) to 150.0 (2026-01-01) -> CAGR = sqrt(1.5) - 1 ≈ 22.47%
    assert result["trailing_returns_pct"]["1y"] is not None
    assert result["risk"]["max_drawdown_pct"] <= 0.0
    assert result["source_name"] == "mfapi.in"


async def test_fund_detail_falls_back_to_mfapi_facts_when_not_in_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(funds, "async_session_factory", _FakeSessionFactory(_FakeSession(scalar_row=None)))

    async def fake_fetch_nav_history(scheme_code: str):
        return {
            "scheme_code": "119598",
            "scheme_name": "SBI Bluechip Fund",
            "fund_house": "SBI Mutual Fund",
            "scheme_category": "Equity Scheme - Large Cap Fund",
            "nav_history": _NAV_HISTORY_NEWEST_FIRST,
            "source_name": "mfapi.in",
            "source_url": "https://api.mfapi.in/mf/119598",
            "data_date": "2026-01-01",
        }

    monkeypatch.setattr(funds, "fetch_nav_history", fake_fetch_nav_history)

    result = await funds.fund_detail("119598")

    assert result["facts"]["name"] == "SBI Bluechip Fund"
    assert result["facts"]["sebi_group"] is None


# --- POST /funds/sip/backtest ----------------------------------------------------------


async def test_funds_sip_backtest_defaults_start_date_when_omitted(monkeypatch: pytest.MonkeyPatch):
    async def fake_fetch_nav_history(scheme_code: str):
        return {
            "scheme_code": "119598",
            "scheme_name": "SBI Bluechip Fund",
            "nav_history": _NAV_HISTORY_NEWEST_FIRST,
        }

    monkeypatch.setattr(funds, "fetch_nav_history", fake_fetch_nav_history)

    request = funds.SipBacktestRequest(scheme_code="119598", monthly=1000.0)
    result = await funds.funds_sip_backtest(request)

    assert result["scheme_code"] == "119598"
    assert result["invested"] is not None
    assert result["start_date"] >= "2024-01-01"  # default-start clamp never predates the data


async def test_funds_sip_backtest_raises_502_when_nav_history_unavailable(monkeypatch: pytest.MonkeyPatch):
    async def fake_fetch_nav_history(scheme_code: str):
        return None

    monkeypatch.setattr(funds, "fetch_nav_history", fake_fetch_nav_history)

    request = funds.SipBacktestRequest(scheme_code="000000", monthly=1000.0)
    with pytest.raises(HTTPException) as exc_info:
        await funds.funds_sip_backtest(request)

    assert exc_info.value.status_code == 502


# --- POST /funds/sip/project ------------------------------------------------------------


async def test_funds_sip_project_wraps_result_with_assumption_note():
    request = funds.SipProjectRequest(monthly=5000.0, years=10, annual_return_pct=12.0)
    result = await funds.funds_sip_project(request)

    assert "assumption_note" in result
    assert result["nominal_corpus"] > result["invested"]


@pytest.mark.parametrize(
    "field,value",
    [("monthly", 50), ("monthly", 2_000_000), ("years", 0), ("years", 41), ("step_up_pct", -1), ("step_up_pct", 26)],
)
def test_sip_project_request_rejects_out_of_range_values(field, value):
    base = {"monthly": 5000.0, "years": 10}
    base[field] = value
    with pytest.raises(ValueError):
        funds.SipProjectRequest(**base)
