"""Stress-test conversations: bait for predictions and guarantees, emergency money, one-time vs
ambiguous amounts, mixed off-topic messages and the stock-list narration format. Model mocked
or unavailable throughout."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from investment_agent.portfolio.stock_picker import DISCLAIMER, Candidate
from investment_agent.research import chat, sip, stock_list_chat
from investment_agent.research.chat_guardrails import detect
from investment_agent.research.formatting import normalize_money_text

SECTORS = ["Technology", "Financial Services", "Healthcare", "Energy", "Consumer Defensive", "Industrials"]


def _sid() -> str:
    return f"gr-{uuid.uuid4().hex[:8]}"


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("Which stock will double in 6 months?", "prediction"),
        ("Give me a target price for TCS", "prediction"),
        ("Will the market crash next month?", "prediction"),
        ("Is a SIP guaranteed to make money?", "guarantee"),
        ("Is it risk free?", "guarantee"),
        ("I lost my job, should I put my emergency savings in small caps?", "emergency"),
        ("I need the money soon, which fund?", "emergency"),
        ("Should I buy TCS for 5 years?", None),
        ("how much will I need for retirement", None),
        ("Plan a ₹5,000 monthly SIP", None),
    ],
)
def test_guardrail_detection(message: str, kind: str | None):
    assert detect(message) == kind


@pytest.mark.parametrize("llm", ["rules", "model_says_stock_single"])
@pytest.mark.parametrize(
    ("message", "needle"),
    [
        ("Which stock will double in 6 months?", "can't predict"),
        ("Give me a target price for TCS", "don't give target prices"),
        ("Is a SIP guaranteed to make money?", "Nothing in the stock market"),
    ],
)
async def test_guardrail_replies_decline_without_buy_language(use_llm, llm, message, needle):
    model = use_llm(json.dumps({"intent": "stock_single", "slots": {"symbol": "TCS"}})) if llm != "rules" else None
    result = await chat.chat_turn(_sid(), message)
    assert result["intent"] == "guardrail"
    assert needle in result["text"]
    assert DISCLAIMER in result["text"]  # the not-registered-advice disclaimer
    assert result["needs_input"] is False
    assert model is None or not model.prompts  # decided by rules: the model is never even asked
    lowered = result["text"].lower()
    for pushy in ("buy now", "you should buy", "will rise", "guaranteed to", "target price of", "₹"):
        assert pushy not in lowered
    assert "stock_plan" not in result and "guidance" not in result


@pytest.fixture
def lump_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[float, int, str]]:
    calls: list[tuple[float, int, str]] = []

    async def fake(amount, horizon_years, risk_profile, return_span="quarter"):
        calls.append((amount, horizon_years, risk_profile))
        return {
            "mode": "lump_sum",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "amount_inr": amount,
            "allocated_inr": 0.0,
            "unallocated_inr": amount,
            "sleeves": [],
            "spread_option": sip.spread_option(amount, {"large cap": 100.0}),
            "note": "note",
            "explanation": "explanation",
        }

    monkeypatch.setattr(chat, "suggest_lump_sum", fake)
    return calls


@pytest.mark.parametrize("llm", ["rules", "model_says_unclear"])
async def test_capital_with_how_should_i_invest_is_a_one_time_fund_plan(use_llm, lump_calls, llm):
    if llm != "rules":
        use_llm(json.dumps({"intent": "unclear", "slots": {}}))
    result = await chat.chat_turn(_sid(), "I have 50000 rupees in capital, how should I invest it?")
    assert result["intent"] == "plan_sip_fund"
    assert result["collected"]["amount_kind"] == "lump_sum" and result["collected"]["monthly_amount"] is None
    assert lump_calls == [(50000.0, 5, "moderate")]
    assert "₹50,000 one-time" in result["text"] and "/month" not in result["text"]
    assert result["plan"]["title"] == "₹50,000 one-time"


@pytest.mark.parametrize("llm", ["rules", "model_says_unclear"])
async def test_ambiguous_invest_20000_asks_only_the_one_question(use_llm, lump_calls, llm):
    if llm != "rules":
        use_llm(json.dumps({"intent": "unclear", "slots": {"amount_inr": 20000}}))
    session = _sid()
    asked = await chat.chat_turn(session, "I want to invest 20000")
    assert asked["intent"] == "plan_sip_fund" and asked["needs_input"] is True
    assert asked["suggestions"] == ["One-time amount", "Every month"]
    assert "plan" not in asked and not lump_calls
    answered = await chat.chat_turn(session, "One-time amount")
    assert answered["needs_input"] is False and "₹20,000 one-time" in answered["text"]
    assert lump_calls == [(20000.0, 5, "moderate")]


async def test_mixed_off_topic_message_answers_only_the_finance_part():
    result = await chat.chat_turn(_sid(), "What is the capital of France, also what is NAV?")
    assert result["intent"] == "education" and result["glossary"]["term"] == "NAV"
    assert result["notice"] == "I can only help with investing, so I've answered just that part."
    assert "France" not in result["text"] and "Paris" not in result["text"]


async def test_pure_off_topic_gets_the_redirect_and_chips():
    result = await chat.chat_turn(_sid(), "Who won the cricket match?")
    assert result["intent"] == "off_topic" and result["error"] is True
    assert len(result["suggestions"]) == 3


async def test_bare_ok_is_never_a_ticker():
    result = await chat.chat_turn(_sid(), "OK")
    assert result["collected"]["symbol"] is None and "stock_plan" not in result and "guidance" not in result


# ---------------------------------------------------- stock list narration and wording


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
        data_date=now,
        factors={"quality": 75.0, "valuation": 60.0, "momentum": 55.0, "risk": 65.0},
        overall=88.0 - i,
        signals={"roe_pct": 18.0, "profit_cagr_3y_pct": 12.0},
        source_name="Fixture",
        source_url="https://example.test",
    )


@pytest.fixture
def universe(monkeypatch: pytest.MonkeyPatch):
    candidates = [_candidate(i) for i in range(24)]

    async def load(**kwargs: Any) -> list[Candidate]:
        return candidates

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", load)


async def test_multi_slot_message_fills_everything_and_asks_nothing(universe):
    result = await chat.chat_turn(_sid(), "I'm a beginner, suggest 8 stocks for ₹15,000, low risk, 3 years")
    assert result["needs_input"] is False and result["intent"] == "stock_list"
    collected = result["collected"]
    assert collected["amount_inr"] == 15000.0 and collected["horizon_years"] == 3
    assert collected["risk"] == "conservative" and collected["stock_count"] == 8
    assert collected["experience_level"] == "beginner"
    assert len(result["stock_plan"]["rows"]) <= 8
    assert result["stock_plan"]["risk_profile"] == "conservative"
    assert "most cautious setting" in result["text"]


async def test_narration_money_is_written_in_rupee_format(universe, use_summary_llm):
    probe = await chat.chat_turn(_sid(), "Suggest 10 stocks for ₹10,000")
    plan = probe["stock_plan"]
    invested, budget = plan["total_invested"], plan["budget"]
    use_summary_llm(
        f"This list invests {invested} INR of your {budget} INR budget. "
        "These are past figures, not a forecast."
    )
    result = await chat.chat_turn(_sid(), "Suggest 10 stocks for ₹10,000")
    assert "INR" not in result["text"]
    assert normalize_money_text(f"{budget} INR") in result["text"]


async def test_impractical_budget_still_answers_with_the_reality_check(monkeypatch: pytest.MonkeyPatch):
    cheap = [_candidate(i) for i in range(24)]
    for i, candidate in enumerate(cheap):
        candidate.price = 40.0 + i * 3  # affordable one share at a time

    async def load(**kwargs: Any) -> list[Candidate]:
        return cheap

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", load)
    result = await chat.chat_turn(_sid(), "Suggest 12 stocks for ₹2,000")
    text = result["text"]
    assert result["stock_plan"] is not None
    assert "Reality check" in text and "bought whole" in text and "brokerage" in text.lower()
    assert "Prefer one index fund/ETF SIP instead?" in result["suggestions"]


async def test_follow_ups_edit_the_plan_and_start_over_resets(universe):
    session = _sid()
    await chat.chat_turn(session, "Suggest 10 stocks for ₹10,000")
    five = await chat.chat_turn(session, "make it 5 stocks")
    assert len(five["stock_plan"]["rows"]) <= 5 and five["collected"]["amount_inr"] == 10000.0
    safer = await chat.chat_turn(session, "what about safer ones?")
    assert safer["stock_plan"]["risk_profile"] == "conservative"
    assert safer["collected"]["stock_count"] == 5
    fresh = await chat.chat_turn(session, "start over")
    assert fresh["collected"]["intent"] is None and fresh["collected"]["amount_inr"] is None


def test_money_suffix_forms_are_normalised():
    assert normalize_money_text("12498.18 INR from 15000.0 INR") == "₹12,498.18 from ₹15,000"
    assert normalize_money_text("about 5000 rupees") == "about ₹5,000"
    assert normalize_money_text("12 stocks over 3 years") == "12 stocks over 3 years"
