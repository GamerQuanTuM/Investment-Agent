"""End-to-end chat behaviour for stock_list, market_overview and portfolio_help, with the
database, market feeds and models all faked."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from investment_agent.portfolio.stock_picker import Candidate
from investment_agent.research import chat, chat_session, stock_list_chat

FAILING_MESSAGE = (
    "I am new to stock market. In current market and future potential give me 10-12 stocks "
    "I can invest for 10000 rupees and also how much to invest in each."
)
SECTORS = ["Technology", "Financial Services", "Healthcare", "Energy", "Consumer Defensive", "Industrials"]


def _candidate(i: int) -> Candidate:
    now = datetime.now(UTC)
    return Candidate(
        symbol=f"STK{i:02d}",
        name=f"Stock {i:02d} Limited",
        sector=SECTORS[i % len(SECTORS)],
        price=300.0 + i * 11,
        price_time=now - timedelta(hours=3),
        market_cap_cr=90_000.0,
        avg_volume=1_500_000.0,
        data_date=now - timedelta(days=20),
        factors={"quality": 75.0, "valuation": 60.0, "momentum": 55.0, "risk": 65.0},
        overall=88.0 - i,
        signals={"roe_pct": 18.0, "profit_cagr_3y_pct": 12.0, "pe_ratio": 22.0, "return_12m_pct": 8.0},
        source_name="Fixture fundamentals",
        source_url="https://example.test/fundamentals",
    )


FIXTURE_UNIVERSE = [_candidate(i) for i in range(24)]
FIXTURE_SYMBOLS = {c.symbol for c in FIXTURE_UNIVERSE}


@pytest.fixture
def universe(monkeypatch: pytest.MonkeyPatch):
    async def load(**kwargs: Any) -> list[Candidate]:
        return FIXTURE_UNIVERSE

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", load)
    return FIXTURE_UNIVERSE


def _sid() -> str:
    return f"sl-{uuid.uuid4().hex[:8]}"


async def test_failing_message_returns_a_stock_list_with_all_slots_filled(universe):
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert result["intent"] == "stock_list"
    assert result["needs_input"] is False
    assert "which company" not in result["text"].lower()
    plan = result["stock_plan"]
    assert 10 <= len(plan["rows"]) <= 12
    assert {r["symbol"] for r in plan["rows"]} <= FIXTURE_SYMBOLS
    assert plan["total_invested"] <= 10_000
    assert plan["leftover"] == pytest.approx(10_000 - plan["total_invested"], abs=0.01)
    assert plan["data_as_of"]
    for key in ("rows", "total_invested", "leftover", "data_as_of", "caveats"):
        assert key in plan
    row = plan["rows"][0]
    for key in ("symbol", "name", "sector", "price", "shares", "amount_inr", "weight_pct", "score", "why"):
        assert key in row
    assert isinstance(row["shares"], int)


async def test_small_budget_gets_the_honest_reality_check_and_the_index_fund_offer(universe):
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert "Reality check" in result["text"]
    assert "brokerage" in result["text"].lower()
    assert "SEBI-registered" in result["text"]
    assert result["stock_plan"]["reality_check"]
    assert "Prefer one index fund/ETF SIP instead?" in result["suggestions"]
    # Beginner extras: jargon explained inline, one-line risk warning.
    assert "small slice of a company" in result["text"]
    assert "fall as well as rise" in result["text"]
    # No forecast language anywhere.
    for banned in ("target price", "expected return", "will rise", "guaranteed"):
        assert banned not in result["text"].lower()


async def test_reply_carries_sources_with_dates(universe):
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    names = {s["source_name"] for s in result["sources"]}
    assert {"INDstocks daily bars", "Fixture fundamentals"} <= names
    assert all(s["data_date"] for s in result["sources"])


async def test_missing_amount_asks_only_for_the_amount(universe):
    result = await chat.chat_turn(_sid(), "Which stocks should I buy?")
    assert result["intent"] == "stock_list"
    assert result["needs_input"] is True
    assert "how much" in result["text"].lower()
    assert "years" not in result["text"].lower()
    assert result["suggestions"]


async def test_empty_universe_says_data_is_not_loaded(monkeypatch: pytest.MonkeyPatch):
    async def empty(**kwargs: Any) -> list[Candidate]:
        return []

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", empty)
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert result["data_status"] == "DATA_UNAVAILABLE"
    assert result["stock_plan"] is None
    assert "market data isn't loaded yet" in result["text"].lower()
    assert "/market/refresh" in result["text"]
    assert not any(sym in result["text"] for sym in FIXTURE_SYMBOLS)


async def test_nothing_passing_the_filters_is_data_unavailable_too(monkeypatch: pytest.MonkeyPatch):
    stale = _candidate(1)
    stale.price_time = datetime.now(UTC) - timedelta(days=30)

    async def load(**kwargs: Any) -> list[Candidate]:
        return [stale]

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", load)
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert result["data_status"] == "DATA_UNAVAILABLE"
    assert "STK01" not in result["text"]


async def test_ungrounded_llm_summary_is_replaced_by_the_template(universe, use_summary_llm):
    llm = use_summary_llm("Buy WIPRO now, it should give 25% and TCS is at ₹4,100.")
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert llm.prompts
    assert "WIPRO" not in result["text"]
    assert "25%" not in result["text"]
    assert stock_list_chat.template_summary(result["stock_plan"], monthly=False) in result["text"]


async def test_grounded_llm_summary_is_used(universe, use_summary_llm):
    use_summary_llm(
        "These are past figures, not a forecast: a spread across several sectors "
        "chosen by quality and valuation, starting with STK00."
    )
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert "starting with STK00" in result["text"]


async def test_llm_numbers_must_come_from_the_result(universe, use_summary_llm):
    use_summary_llm("A spread of 7 sectors with ₹123,456 invested.")
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert "123,456" not in result["text"]


async def test_follow_up_modifies_the_previous_plan_instead_of_restarting(universe):
    session_id = _sid()
    first = await chat.chat_turn(session_id, FAILING_MESSAGE)
    assert len(first["stock_plan"]["rows"]) >= 10
    smaller = await chat.chat_turn(session_id, "make it 8 stocks")
    assert smaller["intent"] == "stock_list"
    assert len(smaller["stock_plan"]["rows"]) <= 8
    assert smaller["collected"]["amount_inr"] == 10000.0  # carried over, not re-asked
    safer = await chat.chat_turn(session_id, "what about safer ones?")
    assert safer["collected"]["risk"] == "conservative"
    assert safer["stock_plan"]["risk_profile"] == "conservative"
    assert safer["collected"]["stock_count"] == 8


async def test_follow_up_survives_a_process_restart_via_redis(universe):
    session_id = _sid()
    await chat.chat_turn(session_id, FAILING_MESSAGE)
    chat_session._memory.clear()  # another worker, same Redis
    again = await chat.chat_turn(session_id, "make it 6 stocks")
    assert len(again["stock_plan"]["rows"]) <= 6


async def test_index_fund_chip_routes_to_suggest_mix_with_the_same_amount(universe, monkeypatch):
    seen: dict[str, Any] = {}

    async def fake_suggest_mix(monthly, horizon_years, risk_profile):
        seen.update(monthly=monthly, horizon=horizon_years, risk=risk_profile)
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [],
            "note": "n",
            "explanation": "e",
        }

    monkeypatch.setattr(chat, "suggest_mix", fake_suggest_mix)
    session_id = _sid()
    await chat.chat_turn(session_id, FAILING_MESSAGE)
    result = await chat.chat_turn(session_id, "Prefer one index fund/ETF SIP instead?")
    assert result["intent"] == "plan_sip_fund"
    assert result["needs_input"] is False
    assert seen == {"monthly": 10000.0, "horizon": 5, "risk": "conservative"}


async def test_stock_list_never_asks_which_company_for_a_count_request(universe):
    for message in ("give me 5 stocks for 20000 rupees", "suggest ten stocks with 50k", "top stocks to buy"):
        result = await chat.chat_turn(_sid(), message)
        assert result["intent"] == "stock_list"
        assert "which company" not in result["text"].lower()


# ----------------------------------------------------------------- market overview


async def test_market_overview_states_only_fetched_numbers(monkeypatch: pytest.MonkeyPatch):
    async def indices():
        return [
            {"name": "Nifty 50", "live_price": 24500.5, "day_change_percentage": 0.42},
            {"name": "Sensex", "live_price": 80100.0, "day_change_percentage": 0.38},
        ]

    async def macro():
        return {
            "usd_inr": {"status": "OK", "value": 83.2, "data_date": "2026-10-03", "source_name": "FRED — DEXINUS", "source_url": "u"},
            "cpi_inflation_yoy": {"status": "DATA_UNAVAILABLE"},
        }

    monkeypatch.setattr("investment_agent.market.board.live_indices", indices)
    monkeypatch.setattr("investment_agent.market.macro.get_macro_snapshot", macro)
    result = await chat.chat_turn(_sid(), "how is the market today")
    assert result["intent"] == "market_overview"
    text = result["text"]
    assert "24,500.50" in text and "+0.42%" in text
    assert "Risk-on" in text
    assert "India VIX (fear gauge): DATA_UNAVAILABLE" in text
    assert "83.2" in text and "2026-10-03" in text
    assert "Consumer inflation: DATA_UNAVAILABLE" in text
    assert {s["source_name"] for s in result["sources"]} >= {"Yahoo Finance", "FRED — DEXINUS"}


async def test_market_overview_without_data_does_not_invent_any(monkeypatch: pytest.MonkeyPatch):
    async def boom():
        raise RuntimeError("feed down")

    monkeypatch.setattr("investment_agent.market.board.live_indices", boom)
    monkeypatch.setattr("investment_agent.market.macro.get_macro_snapshot", boom)
    result = await chat.chat_turn(_sid(), "how is the market today")
    assert result["text"].startswith("DATA_UNAVAILABLE")
    assert not any(ch.isdigit() for ch in result["text"])


# ----------------------------------------------------------------- portfolio help


async def test_portfolio_help_without_holdings_asks_the_user_to_add_them(monkeypatch: pytest.MonkeyPatch):
    async def empty():
        return {"holdings": []}

    monkeypatch.setattr("investment_agent.api.routes.market.portfolio", empty)
    result = await chat.chat_turn(_sid(), "check my portfolio risk")
    assert result["intent"] == "portfolio_help"
    assert "don't see any holdings" in result["text"]


async def test_portfolio_help_reports_concentration_and_alerts(monkeypatch: pytest.MonkeyPatch):
    async def book():
        return {
            "holdings": [
                {"symbol": "AAA", "sector": "Energy", "current_value": 800.0, "allocation_pct": 80.0, "unrealized_pnl_pct": -20.0},
                {"symbol": "BBB", "sector": "Technology", "current_value": 200.0, "allocation_pct": 20.0, "unrealized_pnl_pct": 5.0},
            ]
        }

    monkeypatch.setattr("investment_agent.api.routes.market.portfolio", book)
    result = await chat.chat_turn(_sid(), "how is my portfolio doing, am i too concentrated")
    assert result["intent"] == "portfolio_help"
    assert "Energy at 80" in result["text"]
    assert "AAA is down -20.0%" in result["text"]
    assert "not an instruction to buy or sell" in result["text"]
