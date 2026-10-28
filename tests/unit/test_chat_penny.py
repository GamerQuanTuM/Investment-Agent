"""'Penny stocks' (shares under Rs 10-20) are not covered by the normal list: the agent must ask
what the person means, take a price they already gave, and never silently return the usual list."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from test_chat_stock_list import FIXTURE_UNIVERSE, _sid, universe  # noqa: F401

from investment_agent.research import chat, stock_list_chat

ASK = "Suggest 30 penny stocks for Rs 15000"


@pytest.fixture
def cheap_universe(monkeypatch: pytest.MonkeyPatch):
    stocks = [replace(c, price=8.0 + i * 2) if i < 6 else c for i, c in enumerate(FIXTURE_UNIVERSE)]

    async def load(**kwargs: Any):
        return stocks

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", load)
    return stocks


async def test_penny_request_asks_what_price_counts_instead_of_returning_the_usual_list(cheap_universe):
    asked = await chat.chat_turn(_sid(), ASK)
    assert asked["needs_input"] and not asked.get("stock_plan")
    assert "₹10-20" in asked["text"]
    assert asked["suggestions"][:2] == ["Under ₹10 a share", "Under ₹20 a share"]


async def test_choosing_a_price_limit_returns_only_shares_under_it_with_risk_warning(cheap_universe):
    session_id = _sid()
    await chat.chat_turn(session_id, ASK)
    result = await chat.chat_turn(session_id, "Under ₹20 a share")
    plan = result["stock_plan"]
    assert plan["rows"] and all(r["price"] < 20 for r in plan["rows"])
    assert "high risk" in result["text"]
    assert any("You asked for 30 stocks" in c for c in plan["caveats"])


async def test_a_price_stated_in_the_request_is_used_without_asking(cheap_universe):
    result = await chat.chat_turn(_sid(), "Suggest 10 penny stocks under 12 for Rs 15000")
    assert not result["needs_input"]
    assert result["stock_plan"]["rows"] and all(r["price"] <= 12 for r in result["stock_plan"]["rows"])


async def test_price_limit_says_so_when_nothing_qualifies(universe):  # noqa: F811
    session_id = _sid()
    await chat.chat_turn(session_id, ASK)
    result = await chat.chat_turn(session_id, "Under ₹10 a share")
    assert not result.get("stock_plan")
    assert "won't pad the list" in result["text"]


async def test_keep_safer_list_runs_the_usual_list(universe):  # noqa: F811
    session_id = _sid()
    await chat.chat_turn(session_id, ASK)
    result = await chat.chat_turn(session_id, "Keep the usual safer list")
    assert result["stock_plan"]["rows"]


async def test_unrelated_question_gets_a_polite_scope_message(universe):  # noqa: F811
    result = await chat.chat_turn(_sid(), "What is the best pizza recipe?")
    assert result["intent"] == "off_topic"
    assert "only answer questions about stocks" in result["text"]
