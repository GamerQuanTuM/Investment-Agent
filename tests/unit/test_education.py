"""Education handler: curated glossary needs no market data and never asks for amount/horizon;
the model fallback is boxed in by a system prompt and a mechanical content check."""

from __future__ import annotations

import re
import uuid

import pytest

from investment_agent.research import chat, education
from investment_agent.research.glossary import GLOSSARY, find_term


def _sid() -> str:
    return f"edu-{uuid.uuid4().hex[:8]}"


@pytest.mark.parametrize(
    ("message", "term"),
    [
        ("what is an ETF", "ETF"),
        ("explain SIP", "SIP"),
        ("what is NAV", "NAV"),
        ("what is P/E ratio", "P/E ratio"),
        ("what does expense ratio mean", "Expense ratio"),
        ("tell me about ELSS", "ELSS"),
        ("what is a demat account", "Demat account"),
        ("explain LTCG", "LTCG"),
        ("what is diversification", "Diversification"),
        ("how does the stock market work", "Stock market"),
    ],
)
async def test_glossary_hit_needs_no_market_data_and_asks_nothing(message, term, monkeypatch):
    # Any attempt to touch market data or the funds pipeline would blow up here.
    async def boom(*a, **k):
        raise AssertionError("education must not fetch market data")

    for name in ("suggest_mix", "build_etf_sip", "rank_funds", "guide_symbol"):
        monkeypatch.setattr(chat, name, boom)

    result = await chat.chat_turn(_sid(), message)
    assert result["intent"] == "education"
    assert result["needs_input"] is False
    assert result["glossary"]["term"] == term
    assert result["glossary"]["definition"] in result["text"]
    assert "Example" in result["text"]
    lowered = result["text"].lower()
    assert "how many years" not in lowered and "how much" not in lowered
    assert len(result["suggestions"]) == 1  # one optional next-step chip
    assert result["sources"][0]["source_name"].startswith("Curated")


async def test_next_step_chip_reuses_a_known_amount():
    assert education.next_step_chip("ETF", 8000) == "Plan a ₹8,000 monthly SIP"
    assert education.next_step_chip("P/E ratio", 8000) == "Suggest 10 stocks for ₹8,000"
    assert education.next_step_chip("ETF", None) == "Plan a ₹5,000 monthly SIP"


async def test_education_mid_flow_does_not_lose_the_open_question():
    session_id = _sid()
    await chat.chat_turn(session_id, "monthly SIP")  # asks for the horizon
    explained = await chat.chat_turn(session_id, "what is an ETF")
    assert explained["intent"] == "education"
    resumed = await chat.chat_turn(session_id, "5")
    assert resumed["collected"]["horizon_years"] == 5


def test_every_glossary_entry_is_reviewable():
    assert len(GLOSSARY) >= 20
    terms = {entry.term for entry in GLOSSARY}
    for required in (
        "ETF", "SIP", "Mutual fund", "NAV", "Expense ratio", "P/E ratio", "ROE", "Market cap",
        "Large cap", "Mid cap", "Small cap", "Index fund", "ELSS", "Demat account", "LTCG",
        "STCG", "Diversification", "Dividend", "IPO", "Risk vs return",
    ):
        assert required in terms
    for entry in GLOSSARY:
        assert entry.definition and entry.example
        assert find_term(f"what is {entry.aliases[0]}") is not None
        # Fixed definitions never promise an outcome or name a target.
        for text in (entry.definition, entry.example):
            assert not re.search(r"guaranteed (?:return|profit)|will (?:earn|double)|target price", text, re.IGNORECASE)


async def test_unknown_concept_without_model_admits_it_and_offers_terms():
    result = await chat.chat_turn(_sid(), "what is a bond ladder")
    assert result["intent"] == "education"
    assert "glossary" not in result
    assert "rather not guess" in result["text"]
    assert result["suggestions"]


async def test_unknown_concept_uses_model_under_the_restricted_prompt(use_education_llm, use_llm):
    llm = use_education_llm(
        "A bond ladder means buying bonds that mature at different times, so some money "
        "comes back regularly and you are not stuck with one date."
    )
    result = await chat.chat_turn(_sid(), "what is a bond ladder")
    assert "mature at different times" in result["text"]
    assert result["needs_input"] is False
    prompt = llm.prompts[0]
    for forbidden in ("price", "ticker", "recommend"):
        assert forbidden in prompt
    assert education.EDUCATION_SYSTEM_PROMPT in prompt


@pytest.mark.parametrize(
    "bad_reply",
    [
        "A bond ladder gives about 7% a year.",
        "You should buy TCS before it rises.",
        "It costs ₹5,000 to start.",
        "Bonds are guaranteed to be safe.",
        "Try INFY and RELIANCE for this.",
        "",
    ],
)
async def test_model_reply_with_figures_tickers_or_advice_is_rejected(bad_reply, use_education_llm):
    use_education_llm(bad_reply)
    result = await chat.chat_turn(_sid(), "what is a bond ladder")
    assert bad_reply == "" or bad_reply not in result["text"]
    assert "rather not guess" in result["text"]


def test_check_accepts_clean_plain_language():
    assert education.passes_education_check("An ETF is a basket you buy through a broker. ")
    assert not education.passes_education_check("Returns were 12 last year")
