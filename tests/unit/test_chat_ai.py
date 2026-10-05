"""AI-written answers under guardrails, rich-text (Markdown) formatting, and the human-in-the-loop
confirmation for sensitive questions. The model is mocked (or down: reviewed text is the fallback)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from investment_agent.portfolio.stock_picker import DISCLAIMER, Candidate
from investment_agent.research import chat, stock_list_chat
from investment_agent.research.chat_ai import passes_ai_check

EMERGENCY = "I lost my job, should I put my emergency savings in small caps?"
GOOD_ETF = (
    "An **ETF** is a basket of investments you buy on the exchange, like a single share.\n\n"
    "- You need a **demat account**\n- It usually has *low costs*\n- Prices move during market hours"
)
GOOD_TABLE = (
    "| | ETF | Mutual fund |\n|---|---|---|\n| **Demat account** | Needed | Not needed |\n"
    "| **How you buy** | On the exchange | Directly or via an app |\n\n"
    "- **Bottom line:** a mutual fund is usually simpler to start with."
)


def _sid() -> str:
    return f"ai-{uuid.uuid4().hex[:8]}"


# ------------------------------------------------------------------ the guardrail check


@pytest.mark.parametrize(
    "text",
    [
        GOOD_ETF,
        GOOD_TABLE,
        "A lock-in of 3 years means you can't withdraw earlier. See Section 80C rules.",
        "Compare **SIP** and **lump sum**: a SIP spreads your buying over many months.",
        "Nothing is guaranteed, and I don't give target prices or forecasts.",
    ],
)
def test_check_allows_rich_text_and_plain_numbers(text: str):
    assert passes_ai_check(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "It returned 12% last year.",
        "You would pay ₹500 a month.",
        "Rs 5000 is enough to start.",
        "TCS is a good example.",
        "You should buy this fund now.",
        "This will double your money.",
        "It is guaranteed to grow.",
        "x" * 4000,
    ],
)
def test_check_rejects_figures_tickers_forecasts_and_advice(text: str):
    assert not passes_ai_check(text)


# ------------------------------------------------------------------ AI decides the answer


async def test_a_definition_is_written_by_the_model_in_markdown(use_education_llm):
    llm = use_education_llm(GOOD_ETF)
    result = await chat.chat_turn(_sid(), "what is an ETF?")
    assert result["intent"] == "education"
    assert result["text"] == GOOD_ETF and result["answered_by"] == "ai"
    assert result["glossary"]["term"] == "ETF"  # structured field kept for API clients
    prompt = llm.prompts[0]
    assert "Markdown" in prompt and "REVIEWED REFERENCE" in prompt and "what is an ETF?" in prompt
    assert "NOT mention any price" in prompt


async def test_a_model_slip_falls_back_to_the_reviewed_definition(use_education_llm):
    use_education_llm("An ETF returned 12% last year, buy it now. TCS is one.")
    result = await chat.chat_turn(_sid(), "what is an ETF?")
    assert result["answered_by"] == "reviewed"
    assert result["glossary"]["definition"] in result["text"]
    assert "12%" not in result["text"] and "TCS" not in result["text"]


async def test_a_comparison_is_a_model_written_table_with_the_structured_data_attached(use_education_llm):
    llm = use_education_llm(GOOD_TABLE)
    result = await chat.chat_turn(_sid(), "difference between ETF and mutual fund")
    assert result["intent"] == "compare" and result["text"] == GOOD_TABLE
    assert result["answered_by"] == "ai"
    assert result["comparison"]["columns"] == ["ETF", "Mutual fund"]
    assert "| **How you buy** |" in llm.prompts[0]  # the reviewed table is the model's reference


async def test_a_comparison_falls_back_to_a_markdown_table():
    result = await chat.chat_turn(_sid(), "difference between ETF and mutual fund")
    assert result["answered_by"] == "reviewed"
    assert "| | ETF | Mutual fund |" in result["text"] and "|---|---|---|" in result["text"]
    assert "**Which is simpler for a beginner?**" in result["text"]


async def test_prediction_bait_is_answered_by_the_model_and_still_ends_with_the_disclaimer(use_education_llm):
    llm = use_education_llm(
        "I can't predict prices, and nobody can.\n\n- I can show **past quality**\n- and *recent trend*"
    )
    result = await chat.chat_turn(_sid(), "Which stock will double in 6 months?")
    assert result["intent"] == "guardrail" and result["answered_by"] == "ai"
    assert result["text"].startswith("I can't predict prices, and nobody can.")
    assert f"*{DISCLAIMER}*" in result["text"]
    assert "Politely decline" in llm.prompts[0]


async def test_a_model_that_complies_with_prediction_bait_is_replaced_by_the_reviewed_decline(use_education_llm):
    use_education_llm("Sure! This stock will double in 6 months, so you should buy it now.")
    result = await chat.chat_turn(_sid(), "Which stock will double in 6 months?")
    assert result["answered_by"] == "reviewed"
    assert "I can't predict prices" in result["text"] and "will double" not in result["text"].replace(
        "which stock will double", ""
    )
    assert DISCLAIMER in result["text"]


# ----------------------------------------------------------------- human in the loop


async def test_emergency_money_question_is_held_until_the_user_confirms(use_education_llm):
    llm = use_education_llm("should never be shown before confirmation")
    session = _sid()
    held = await chat.chat_turn(session, EMERGENCY)
    assert held["needs_input"] is True and held["intent"] == "guardrail"
    assert held["suggestions"] == ["Yes, continue", "No, stop"]
    assert held["hitl"] == {"required": True, "kind": "emergency", "status": "awaiting_confirmation"}
    assert "general education" in held["text"] and "small cap" not in held["text"].lower()
    assert not llm.prompts  # nothing was answered, nothing was sent to a model yet

    answered = await chat.chat_turn(session, "Yes, continue")
    assert answered["hitl"]["status"] == "confirmed" and answered["needs_input"] is False
    assert answered["guardrail"] == "emergency"
    assert "emergency money" in llm.prompts[0].lower() or "emergency savings" in llm.prompts[0].lower()
    assert DISCLAIMER in answered["text"] and "SEBI-registered adviser" in answered["text"]


async def test_confirmed_emergency_answer_falls_back_to_reviewed_text():
    session = _sid()
    await chat.chat_turn(session, EMERGENCY)
    answered = await chat.chat_turn(session, "yes")
    assert answered["answered_by"] == "reviewed"
    text = answered["text"].lower()
    assert "please don't put emergency savings into small caps" in text and "fixed deposit" in text
    assert "no investment outcome can be promised" in text


async def test_declining_stops_without_answering():
    session = _sid()
    await chat.chat_turn(session, EMERGENCY)
    stopped = await chat.chat_turn(session, "No, stop")
    assert stopped["hitl"]["status"] == "declined"
    assert "stopped here" in stopped["text"] and "small cap" not in stopped["text"].lower()
    again = await chat.chat_turn(session, "yes")  # nothing pending any more
    assert "hitl" not in again


async def test_all_in_questions_are_also_held():
    held = await chat.chat_turn(_sid(), "I want to put all my savings in one stock")
    assert held["hitl"]["kind"] == "all_in" and held["needs_input"] is True


async def test_moving_on_after_the_confirmation_prompt_clears_it():
    session = _sid()
    await chat.chat_turn(session, EMERGENCY)
    other = await chat.chat_turn(session, "what is an ETF?")
    assert other["intent"] == "education" and "hitl" not in other
    late_yes = await chat.chat_turn(session, "yes")
    assert "hitl" not in late_yes


async def test_a_definition_question_about_emergency_money_is_not_held():
    result = await chat.chat_turn(_sid(), "what is an emergency fund?")
    assert "hitl" not in result


async def test_non_sensitive_guardrails_are_not_held():
    result = await chat.chat_turn(_sid(), "Is a SIP guaranteed to make money?")
    assert "hitl" not in result and result["guardrail"] == "guarantee"


# ------------------------------------------------------------------- rich text output


async def test_fund_plan_text_is_markdown_bullets_with_bold_names(monkeypatch: pytest.MonkeyPatch):
    async def mix(monthly, horizon_years, risk_profile):
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [
                {
                    "category": "large cap",
                    "category_label": "large, well-established companies",
                    "weight_pct": 100.0,
                    "monthly_inr": monthly,
                    "status": "OK",
                    "scheme_code": "1",
                    "scheme_name": "Alpha Bluechip Fund - Direct Plan - Growth",
                    "trailing_return_pct_used": 3.2,
                    "return_window": "this quarter",
                }
            ],
            "note": "n",
            "explanation": "e",
        }

    monkeypatch.setattr(chat, "suggest_mix", mix)
    result = await chat.chat_turn(_sid(), "I am new. Plan a SIP of ₹5,000 per month")
    text = result["text"]
    assert "- **large, well-established companies — Alpha Bluechip Fund - Direct Plan - Growth**:" in text
    assert "For **₹5,000/month**" in text
    assert text.startswith("*Since you're new, I assumed **5 years and a balanced mix**")


async def test_stock_list_text_is_a_numbered_list_with_bold_symbols(monkeypatch: pytest.MonkeyPatch):
    now = datetime.now(UTC)
    sectors = ["Technology", "Financial Services", "Healthcare", "Energy", "Consumer Defensive", "Industrials"]
    candidates = [
        Candidate(
            symbol=f"STK{i:02d}",
            name=f"Stock {i}",
            sector=sectors[i % 6],
            price=100.0 + i,
            price_time=now - timedelta(hours=2),
            market_cap_cr=90_000.0,
            avg_volume=1_000_000.0,
            data_date=now,
            factors={"quality": 75.0, "valuation": 60.0, "momentum": 55.0, "risk": 65.0},
            overall=90.0 - i,
            signals={},
            source_name="Fixture",
            source_url="https://example.test",
        )
        for i in range(24)
    ]

    async def load(**kwargs: Any) -> list[Candidate]:
        return candidates

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", load)
    result = await chat.chat_turn(_sid(), "Suggest 10 stocks for ₹10,000")
    assert "1. **STK00** (" in result["text"]
    assert f"*{DISCLAIMER}*" in result["text"]


@pytest.mark.parametrize(
    "text",
    [
        "No one knows which stock will double or what a share will be worth.",
        "I can't say whether it will rise, so I don't give target prices.",
    ],
)
def test_check_allows_denials_that_mention_a_forecast(text: str):
    assert passes_ai_check(text)


def test_check_still_rejects_a_bare_forecast():
    assert not passes_ai_check("This stock will double soon.")
    assert not passes_ai_check("Buy it: it will rise next week.")
