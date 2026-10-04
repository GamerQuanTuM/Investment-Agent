"""Wiring tests for research/sip.py: the ETF mix (build_etf_sip, relabelled from
build_sip, LLM style-classifier removed in B4), the single-fund SIP builder
(build_fund_sip), and the suggest-a-mix builder (suggest_mix). All I/O (live quotes,
mfapi.in NAV history, the fund candidate DB query, the LLM) is monkeypatched — this
verifies assembly, not the underlying math (see test_fund_metrics.py for that)."""

from __future__ import annotations

import pytest

from investment_agent.db.models.market import MutualFundScheme
from investment_agent.research import sip

# --- build_etf_sip -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_live_price(monkeypatch: pytest.MonkeyPatch):
    async def fake_live_price(symbol: str):
        return 100.0

    monkeypatch.setattr(sip, "_live_price", fake_live_price)


async def test_build_etf_sip_keeps_requested_style_deterministically():
    result = await sip.build_etf_sip(10000.0, 10, "mid")

    assert result["mode"] == "etf"
    assert result["style"] == "mid"
    assert result["requested_style"] == "mid"
    assert len(result["sleeves"]) == len(sip.MIXES["mid"])
    assert sum(s["weight_pct"] for s in result["sleeves"]) == 100


async def test_build_etf_sip_short_horizon_downgrades_small_to_flexi():
    result = await sip.build_etf_sip(10000.0, 3, "small")

    assert result["style"] == "flexi"


async def test_build_etf_sip_unknown_style_defaults_to_flexi():
    result = await sip.build_etf_sip(5000.0, 5, "not-a-real-style")

    assert result["style"] == "flexi"


# --- build_fund_sip ------------------------------------------------------------------


_NAV_HISTORY = [
    {"date": "2026-01-01", "nav": 180.0},
    {"date": "2025-01-01", "nav": 150.0},
    {"date": "2024-01-01", "nav": 130.0},
    {"date": "2023-01-01", "nav": 110.0},
    {"date": "2021-01-01", "nav": 90.0},
    {"date": "2020-01-01", "nav": 70.0},
]


async def test_build_fund_sip_data_unavailable_when_history_missing(monkeypatch: pytest.MonkeyPatch):
    async def fake_fetch_nav_history(scheme_code: str):
        return None

    monkeypatch.setattr(sip, "fetch_nav_history", fake_fetch_nav_history)

    result = await sip.build_fund_sip("000000", 5000.0, 10)

    assert result["status"] == "DATA_UNAVAILABLE"


async def test_build_fund_sip_assembles_backtest_projection_and_tax(monkeypatch: pytest.MonkeyPatch):
    async def fake_fetch_nav_history(scheme_code: str):
        return {
            "scheme_code": "119598",
            "scheme_name": "Fake Equity Fund",
            "scheme_category": "Equity Scheme - Large Cap Fund",
            "nav_history": _NAV_HISTORY,
        }

    async def fake_explain(scheme_name, backtest, projection, tax):
        return "stubbed explanation"

    monkeypatch.setattr(sip, "fetch_nav_history", fake_fetch_nav_history)
    monkeypatch.setattr(sip, "_explain_fund_sip", fake_explain)

    result = await sip.build_fund_sip("119598", 5000.0, 10, step_up_pct=5.0, inflation_pct=4.0)

    assert result["mode"] == "fund"
    assert result["status"] == "OK"
    assert result["scheme_name"] == "Fake Equity Fund"
    assert result["assumed_annual_return_pct"] is not None
    assert result["backtest"]["invested"] is not None
    assert result["projection"]["assumption_note"] == "This is an assumption, not a forecast."
    assert result["tax_estimate"]["tax_type"] in {"LTCG", "STCG", "NONE"}  # equity fund -> never DATA_UNAVAILABLE
    assert result["explanation"] == "stubbed explanation"


async def test_build_fund_sip_debt_fund_refuses_tax_estimate(monkeypatch: pytest.MonkeyPatch):
    async def fake_fetch_nav_history(scheme_code: str):
        return {
            "scheme_code": "999999",
            "scheme_name": "Fake Debt Fund",
            "scheme_category": "Debt Scheme - Corporate Bond Fund",
            "nav_history": _NAV_HISTORY,
        }

    async def fake_explain(scheme_name, backtest, projection, tax):
        return "stubbed"

    monkeypatch.setattr(sip, "fetch_nav_history", fake_fetch_nav_history)
    monkeypatch.setattr(sip, "_explain_fund_sip", fake_explain)

    result = await sip.build_fund_sip("999999", 5000.0, 10)

    assert result["tax_estimate"]["tax_type"] == "DATA_UNAVAILABLE"


# --- suggest_mix ------------------------------------------------------------------------


def _make_scheme(scheme_code: str, name: str, sebi_group: str) -> MutualFundScheme:
    return MutualFundScheme(
        scheme_code=scheme_code,
        name=name,
        fund_house="Fake AMC",
        category="Equity",
        sebi_group=sebi_group,
        plan="direct",
        option="growth",
    )


async def test_suggest_mix_conservative_short_horizon_overrides_aggressive_request(monkeypatch: pytest.MonkeyPatch):
    async def fake_candidates_for_group(sebi_group: str, limit: int):
        return [_make_scheme(f"{sebi_group}1", f"{sebi_group.title()} Fund", sebi_group)]

    async def fake_best_pick(scheme: MutualFundScheme, span_years: float = 5.0):
        return {"scheme": scheme, "history": {}, "score": 10.0, "annual_score": 10.0, "has_5y_history": True}

    async def fake_explain(risk_profile, horizon_years, sleeves):
        return "stubbed explanation"

    monkeypatch.setattr(sip, "_candidates_for_group", fake_candidates_for_group)
    monkeypatch.setattr(sip, "_best_pick", fake_best_pick)
    monkeypatch.setattr(sip, "_explain_suggestion", fake_explain)

    result = await sip.suggest_mix(10000.0, horizon_years=2, risk_profile="aggressive")

    assert result["mode"] == "suggest"
    groups = {s["category"] for s in result["sleeves"]}
    assert groups == set(sip._RISK_WEIGHTS["conservative"].keys())
    assert all(s["status"] == "OK" for s in result["sleeves"])
    assert sum(s["weight_pct"] for s in result["sleeves"]) == 100.0


async def test_suggest_mix_marks_sleeve_data_unavailable_when_no_candidates(monkeypatch: pytest.MonkeyPatch):
    async def fake_candidates_for_group(sebi_group: str, limit: int):
        return []  # scheme master not synced yet

    async def fake_explain(risk_profile, horizon_years, sleeves):
        return "stubbed"

    monkeypatch.setattr(sip, "_candidates_for_group", fake_candidates_for_group)
    monkeypatch.setattr(sip, "_explain_suggestion", fake_explain)

    result = await sip.suggest_mix(10000.0, horizon_years=10, risk_profile="moderate")

    assert all(s["status"] == "DATA_UNAVAILABLE" for s in result["sleeves"])
    assert all(s["scheme_code"] is None for s in result["sleeves"])


async def test_suggest_mix_unknown_risk_profile_defaults_to_moderate(monkeypatch: pytest.MonkeyPatch):
    async def fake_candidates_for_group(sebi_group: str, limit: int):
        return []

    async def fake_explain(risk_profile, horizon_years, sleeves):
        return "stubbed"

    monkeypatch.setattr(sip, "_candidates_for_group", fake_candidates_for_group)
    monkeypatch.setattr(sip, "_explain_suggestion", fake_explain)

    result = await sip.suggest_mix(10000.0, horizon_years=10, risk_profile="not-a-real-profile")

    groups = {s["category"] for s in result["sleeves"]}
    assert groups == set(sip._RISK_WEIGHTS["moderate"].keys())
