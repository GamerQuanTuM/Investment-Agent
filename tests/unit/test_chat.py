"""Tests for research/chat.py's beginner-friendly flow: terse numeric answers ("5", not
"5 years"), "I don't know" defaults, and routing a mutual-fund request to suggest_mix
(real funds) rather than the ETF calculator. All I/O (suggest_mix, build_etf_sip,
guide_symbol) is monkeypatched."""

from __future__ import annotations

import uuid

import pytest

from investment_agent.research import chat, chat_session


async def test_off_topic_message_returns_error_and_keeps_state():
    session_id = _new_session()
    result = await chat.chat_turn(session_id, "what is the weather today")
    assert result["error"] is True
    assert result["needs_input"] is False
    assert result["intent"] == "off_topic"
    assert len(result["suggestions"]) >= 2
    assert (await chat_session.load_session(session_id))["intent"] is None


async def test_name_some_funds_returns_ranked_list_not_categories(monkeypatch: pytest.MonkeyPatch):
    async def fake_rank_funds(risk, years, total=12):
        return [
            {"rank": 1, "category": "debt", "category_label": "safer, bond-like investments", "scheme_name": "Fund A", "trailing_return_pct": 7.1, "return_window": "5y"},
            {"rank": 2, "category": "large cap", "category_label": "large, well-established companies", "scheme_name": "Fund B", "trailing_return_pct": 12.0, "return_window": "5y"},
        ]

    monkeypatch.setattr(chat, "rank_funds", fake_rank_funds)
    result = await chat.chat_turn(_new_session(), "Which mutual funds should I invest in.. Name some")
    assert [r["scheme_name"] for r in result["ranking"]] == ["Fund A", "Fund B"]
    assert "1. Fund A" in result["text"]


def _new_session() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


async def test_terse_numeric_answers_are_understood_in_context(monkeypatch: pytest.MonkeyPatch):
    """A beginner answering just "5" to "how many years" and just "5000" to "how much"
    (no "years"/"₹" suffix) must still be understood -- this was the exact gap that made
    the original flow feel hostile to someone who doesn't know the expected phrasing."""

    async def fake_suggest_mix(monthly, horizon_years, risk_profile):
        assert monthly == 5000.0
        assert horizon_years == 5
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [],
            "note": "note",
            "explanation": "explanation",
        }

    monkeypatch.setattr(chat, "suggest_mix", fake_suggest_mix)

    session_id = _new_session()
    r1 = await chat.chat_turn(session_id, "I want to invest in mutual funds")
    # "mutual funds" already implies the SIP intent, so the very next question is the
    # horizon question -- it isn't re-asked for intent.
    assert r1["needs_input"] is True
    assert "years" in r1["text"].lower()

    r2 = await chat.chat_turn(session_id, "5")  # answers "how many years"
    assert r2["needs_input"] is True
    assert r2["collected"]["horizon_years"] == 5

    r3 = await chat.chat_turn(session_id, "5000")  # answers "how much per month"
    assert r3["needs_input"] is True
    assert r3["collected"]["monthly_amount"] == 5000.0

    r4 = await chat.chat_turn(session_id, "B")  # answers the risk-comfort question
    assert r4["needs_input"] is False
    assert r4["collected"]["risk"] == "moderate"


async def test_uncertain_answer_to_risk_question_defaults_to_moderate(monkeypatch: pytest.MonkeyPatch):
    async def fake_suggest_mix(monthly, horizon_years, risk_profile):
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [],
            "note": "note",
            "explanation": "explanation",
        }

    monkeypatch.setattr(chat, "suggest_mix", fake_suggest_mix)

    session_id = _new_session()
    await chat.chat_turn(session_id, "monthly SIP")
    await chat.chat_turn(session_id, "5 years")
    await chat.chat_turn(session_id, "10000 rupees per month")
    result = await chat.chat_turn(session_id, "I don't know")

    assert result["needs_input"] is False
    assert result["collected"]["risk"] == "moderate"


async def test_uncertain_answer_to_horizon_question_defaults_to_five_years(monkeypatch: pytest.MonkeyPatch):
    async def fake_suggest_mix(monthly, horizon_years, risk_profile):
        assert horizon_years == 5
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [],
            "note": "note",
            "explanation": "explanation",
        }

    monkeypatch.setattr(chat, "suggest_mix", fake_suggest_mix)

    session_id = _new_session()
    await chat.chat_turn(session_id, "monthly SIP")
    r = await chat.chat_turn(session_id, "not sure")
    assert r["collected"]["horizon_years"] == 5


async def test_mutual_fund_request_routes_to_suggest_mix_not_etf(monkeypatch: pytest.MonkeyPatch):
    """The exact bug this session's feedback was about: asking about "mutual funds"
    must call the real-fund suggester, not the ETF calculator."""
    called = {"suggest_mix": False, "build_etf_sip": False}

    async def fake_suggest_mix(monthly, horizon_years, risk_profile):
        called["suggest_mix"] = True
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [
                {
                    "category": "large cap",
                    "weight_pct": 100.0,
                    "monthly_inr": monthly,
                    "status": "OK",
                    "scheme_code": "119598",
                    "scheme_name": "SBI Large Cap Fund",
                }
            ],
            "note": "note",
            "explanation": "explanation",
        }

    async def fake_build_etf_sip(*args, **kwargs):
        called["build_etf_sip"] = True
        raise AssertionError("should not be called for a mutual-fund request")

    monkeypatch.setattr(chat, "suggest_mix", fake_suggest_mix)
    monkeypatch.setattr(chat, "build_etf_sip", fake_build_etf_sip)

    session_id = _new_session()
    await chat.chat_turn(session_id, "Which mutual funds should I invest in?")
    await chat.chat_turn(session_id, "5")
    await chat.chat_turn(session_id, "50000")
    result = await chat.chat_turn(session_id, "B")

    assert called["suggest_mix"] is True
    assert called["build_etf_sip"] is False
    assert result["needs_input"] is False
    assert "SBI Large Cap Fund" in result["plan"]["sleeves"][0]["label"]
    # Category jargon is translated to plain language, not shown raw.
    assert "large, well-established companies" in result["plan"]["sleeves"][0]["label"]


async def test_explicit_etf_request_routes_to_build_etf_sip(monkeypatch: pytest.MonkeyPatch):
    async def fake_build_etf_sip(monthly, horizon_years, style):
        assert style == "flexi"  # "moderate" risk maps to "flexi" cap style
        return {
            "mode": "etf",
            "style": style,
            "requested_style": style,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [{"symbol": "NIFTYBEES", "label": "Large cap", "weight_pct": 100, "monthly_inr": monthly, "live_price": 250.0, "units": 4.0}],
            "note": "note",
        }

    monkeypatch.setattr(chat, "build_etf_sip", fake_build_etf_sip)

    session_id = _new_session()
    await chat.chat_turn(session_id, "I want an ETF SIP")
    await chat.chat_turn(session_id, "5")
    await chat.chat_turn(session_id, "5000")
    result = await chat.chat_turn(session_id, "balanced")

    assert result["needs_input"] is False
    assert result["plan"]["sleeves"][0]["symbol"] == "NIFTYBEES"


async def test_stock_intent_skips_risk_question(monkeypatch: pytest.MonkeyPatch):
    async def fake_guide_symbol(symbol, horizon_years, monthly_budget):
        return {"symbol": symbol, "stance": "CONSIDER", "summary": "Looks fine."}

    monkeypatch.setattr(chat, "guide_symbol", fake_guide_symbol)

    session_id = _new_session()
    await chat.chat_turn(session_id, "Should I buy one stock, TCS?")
    await chat.chat_turn(session_id, "5")
    result = await chat.chat_turn(session_id, "5000")

    assert result["needs_input"] is False
    assert result["guidance"]["symbol"] == "TCS"


async def test_failing_beginner_message_never_asks_which_company(monkeypatch: pytest.MonkeyPatch):
    """The original bug: a multi-stock request was routed to the single-stock path and asked
    "Which company?". It must now be a stock_list request with every slot filled at once."""
    result = await chat.chat_turn(_new_session(), FAILING_MESSAGE)
    assert result["intent"] == "stock_list"
    assert "which company" not in result["text"].lower()
    assert result["collected"]["amount_inr"] == 10000.0
    assert result["collected"]["stock_count"] == 12
    assert result["collected"]["experience_level"] == "beginner"


async def test_unknown_all_caps_word_is_never_a_ticker():
    result = await chat.chat_turn(_new_session(), "Should I buy ZZQX for 5 years?")
    assert result["collected"]["symbol"] is None
    assert result["needs_input"] is True
    assert result["suggestions"]  # pick from real symbols, not an invented one
    assert all(s.split(" ")[0] in {"RELIANCE", "TCS", "HDFCBANK", "INFY"} for s in result["suggestions"])


async def test_ambiguous_company_name_offers_choices(monkeypatch: pytest.MonkeyPatch):
    result = await chat.chat_turn(_new_session(), "tell me about tata stock")
    assert result["needs_input"] is True
    symbols = {s.split(" ")[0] for s in result["suggestions"]}
    assert symbols == {"TCS", "TATAMOTORS"}


async def test_unclear_message_asks_one_question_with_chips():
    result = await chat.chat_turn(_new_session(), "asdkj qwlkj zzz")
    assert result["intent"] == "unclear"
    assert result["needs_input"] is True
    assert 3 <= len(result["suggestions"]) <= 4


async def test_beginner_start_gets_starter_chips():
    result = await chat.chat_turn(_new_session(), "I'm new, where do I start?")
    assert result["intent"] == "unclear"
    assert result["suggestions"] == chat.STARTER_SUGGESTIONS


async def test_start_over_resets_the_conversation():
    session_id = _new_session()
    await chat.chat_turn(session_id, "monthly SIP")
    reset = await chat.chat_turn(session_id, "start over")
    assert reset["collected"]["intent"] is None
    state = await chat_session.load_session(session_id)
    assert state["intent"] is None and state["slots"] == {}


async def test_sip_after_stock_list_reuses_the_amount():
    session_id = _new_session()
    await chat_session.save_session(
        session_id,
        {
            **chat_session.new_state(),
            "last_result": {
                "intent": "stock_list",
                "slots": {"amount_inr": 10000.0, "horizon_years": 5, "risk_profile": "moderate"},
            },
        },
    )
    result = await chat.chat_turn(session_id, "Show me an index fund SIP instead")
    assert result["intent"] == "plan_sip_fund"
    assert result["needs_input"] is False
    assert result["collected"]["monthly_amount"] == 10000.0


FAILING_MESSAGE = (
    "I am new to stock market. In current market and future potential give me 10-12 stocks "
    "I can invest for 10000 rupees and also how much to invest in each."
)
