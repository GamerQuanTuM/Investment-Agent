"""Bug 3: "What is the difference between ETF and normal mutual fund" used to return only the
"Mutual fund" definition. The chat now has a `compare` intent that resolves both terms."""

from __future__ import annotations

import json
import uuid

import pytest

from investment_agent.research import chat
from investment_agent.research.chat_intent import extract_slots
from investment_agent.research.glossary import (
    _CURATED,
    COMPARISON_ROWS,
    compare_terms,
    find_term,
    find_terms,
    split_comparison_sides,
)

FAILING_MESSAGE = "What is the difference between ETF and normal mutual fund"


def _sid() -> str:
    return f"cmp-{uuid.uuid4().hex[:8]}"


def _llm_says(intent: str) -> str:
    return json.dumps({"intent": intent, "slots": {}})


@pytest.mark.parametrize("llm", ["rules", "model_says_education", "model_says_unclear"])
async def test_the_exact_failing_message_compares_both_terms(use_llm, llm):
    if llm != "rules":
        use_llm(_llm_says("education" if llm == "model_says_education" else "unclear"))
    result = await chat.chat_turn(_sid(), FAILING_MESSAGE)
    assert result["intent"] == "compare"
    assert result["needs_input"] is False
    comparison = result["comparison"]
    assert comparison["columns"] == ["ETF", "Mutual fund"]
    assert [row["label"] for row in comparison["rows"]] == list(COMPARISON_ROWS)
    assert all(row["a"] and row["b"] for row in comparison["rows"])
    assert "demat" in comparison["rows"][1]["a"].lower() or comparison["rows"][1]["a"] == "Yes."
    assert comparison["rows"][1]["b"] == "No."
    assert comparison["takeaway"]
    # the text carries both sides, not one definition
    assert "ETF" in result["text"] and "Mutual fund" in result["text"]
    assert "Which is simpler for a beginner?" in result["text"]
    assert "Plan a SIP in a mutual fund" in result["suggestions"]
    assert "What is NAV?" in result["suggestions"]
    assert result["sources"] and result["sources"][0]["source_name"].startswith("Curated beginner")
    assert "glossary" not in result  # not the single-definition card


async def test_compare_slots_name_both_terms():
    slots = extract_slots(FAILING_MESSAGE)
    assert (slots.term_a, slots.term_b) == ("ETF", "Mutual fund")


async def test_order_follows_the_question():
    result = await chat.chat_turn(_sid(), "mutual fund vs ETF")
    assert result["comparison"]["columns"] == ["Mutual fund", "ETF"]
    row = result["comparison"]["rows"][1]
    assert (row["a"], row["b"]) == ("No.", "Yes.")


@pytest.mark.parametrize(
    ("message", "columns"),
    [
        ("SIP vs lump sum", ["SIP", "Lump sum"]),
        ("ETF or index fund", ["ETF", "Index fund"]),
        ("Which is better, SIP or lump sum?", ["SIP", "Lump sum"]),
        ("index fund vs active fund", ["Index fund", "Actively managed fund"]),
        ("difference between direct and regular plan", ["Direct plan", "Regular plan"]),
        ("growth vs IDCW/dividend option", ["Growth option", "IDCW (dividend) option"]),
        ("stocks or mutual funds, which is better?", ["Stocks", "Mutual fund"]),
        ("ELSS vs normal equity fund", ["ELSS", "Equity fund"]),
        ("FD vs mutual fund", ["Fixed deposit", "Mutual fund"]),
        ("compare equity and debt fund", ["Equity fund", "Debt fund"]),
        ("how is a SIP different from a lump sum?", ["SIP", "Lump sum"]),
    ],
)
async def test_other_comparisons_are_recognised(message: str, columns: list[str]):
    result = await chat.chat_turn(_sid(), message)
    assert result["intent"] == "compare", message
    assert result["comparison"]["columns"] == columns


async def test_three_way_cap_comparison_has_three_columns():
    result = await chat.chat_turn(_sid(), "large vs mid vs small cap")
    comparison = result["comparison"]
    assert comparison["columns"] == ["Large cap", "Mid cap", "Small cap"]
    assert all(row["a"] and row["b"] and row["c"] for row in comparison["rows"])


async def test_stock_comparison_offers_a_stock_list_chip():
    result = await chat.chat_turn(_sid(), "stocks vs mutual funds")
    assert "Suggest 10 stocks for ₹10,000" in result["suggestions"]


async def test_single_definitions_are_unchanged():
    for message, term in (("what is ETF", "ETF"), ("what is a mutual fund", "Mutual fund"), ("ETF?", "ETF")):
        result = await chat.chat_turn(_sid(), message)
        assert result["intent"] == "education", message
        assert result["glossary"]["term"] == term
        assert "comparison" not in result


def test_find_terms_returns_every_term_in_order_and_find_term_is_unchanged():
    assert [e.term for e in find_terms("difference between ETF and normal mutual fund")] == ["ETF", "Mutual fund"]
    assert [e.term for e in find_terms("SIP or lump sum, which is better")] == ["SIP"]
    # a longer alias is one term, not two ("index mutual fund" is not also "mutual fund")
    assert [e.term for e in find_terms("index mutual fund")] == ["Index fund"]
    assert find_term("ETF and mutual fund").term == "Mutual fund"  # single-term lookup behaviour kept


def test_every_curated_comparison_is_complete_and_has_no_changing_numbers():
    assert len(_CURATED) >= 10
    for keys, takeaway in _CURATED:
        sides = list(keys)
        comparison = compare_terms(sides)
        assert comparison is not None and comparison.curated, keys
        assert len(comparison.rows) == len(COMPARISON_ROWS)
        assert takeaway and takeaway == comparison.takeaway
        for row in comparison.rows:
            assert len(row) == 1 + len(keys)
            for cell in row[1:]:
                assert cell.strip()
                assert not any(sign in cell for sign in ("₹", "%")), (keys, cell)


async def test_two_glossary_terms_without_a_curated_table_are_composed_from_definitions():
    result = await chat.chat_turn(_sid(), "difference between NAV and P/E")
    assert result["intent"] == "compare"
    comparison = result["comparison"]
    assert comparison["columns"] == ["NAV", "P/E ratio"]
    labels = [row["label"] for row in comparison["rows"]]
    assert labels == ["What it is", "Example"]
    from investment_agent.research.glossary import entry_by_term

    nav, pe = entry_by_term("NAV"), entry_by_term("P/E ratio")
    assert comparison["rows"][0]["a"] == nav.definition and comparison["rows"][0]["b"] == pe.definition
    assert result["sources"][0]["source_name"] == "Curated beginner glossary (reviewed definitions)"


async def test_unknown_term_uses_the_guarded_model(use_education_llm):
    llm = use_education_llm(
        "An ETF is a basket you buy on the exchange. Gold is a metal people hold as a store of value. "
        "They behave differently and carry different risks."
    )
    result = await chat.chat_turn(_sid(), "what is the difference between ETF and gold")
    assert result["intent"] == "compare"
    assert llm.prompts and "NOT mention any price" in llm.prompts[0]
    assert "basket you buy on the exchange" in result["text"]
    assert "comparison" not in result


async def test_model_reply_with_figures_or_advice_is_rejected(use_education_llm):
    use_education_llm("Gold gave 12% last year and you should buy it, TCS is cheaper at ₹4,100.")
    result = await chat.chat_turn(_sid(), "what is the difference between ETF and gold")
    assert "12%" not in result["text"] and "TCS" not in result["text"]
    assert "reviewed comparison" in result["text"]
    assert "What is ETF?" in result["suggestions"]


async def test_unknown_term_with_the_model_down_says_so_honestly():
    result = await chat.chat_turn(_sid(), "what is the difference between ETF and bitcoin")
    assert result["intent"] == "compare"
    assert "I'd rather not guess" in result["text"]
    assert result["needs_input"] is False


async def test_comparing_real_securities_is_not_a_term_comparison():
    result = await chat.chat_turn(_sid(), "difference between TCS and INFY")
    assert result["intent"] != "compare"


async def test_an_answer_to_a_pending_question_is_not_a_comparison():
    session = _sid()
    await chat.chat_turn(session, "monthly SIP")
    reply = await chat.chat_turn(session, "5 years or 10 years")
    assert reply["intent"] != "compare"


def test_split_requires_a_comparison_phrasing():
    assert split_comparison_sides("what is ETF") is None
    assert split_comparison_sides("I want to invest in an ETF or two") is not None  # phrasing only
    assert split_comparison_sides("Suggest 10 stocks for ₹10,000") is None


@pytest.mark.parametrize(
    "message",
    ["Suggest stocks or mutual funds for 10000 rupees", "Give me ETF or index fund options", "invest 5000 in stocks or funds"],
)
async def test_a_request_that_mentions_two_products_is_not_a_comparison(message: str):
    result = await chat.chat_turn(_sid(), message)
    assert result["intent"] != "compare", message
