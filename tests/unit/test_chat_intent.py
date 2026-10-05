"""Intent + slot extraction: every case runs twice, once with the rules alone (LLM down) and
once with a mocked LLM that returns the right JSON, so both producers are pinned."""

from __future__ import annotations

import json

import pytest

from investment_agent.research import chat_intent
from investment_agent.research.chat_intent import extract, resolve_symbols, search_universe

FAILING = (
    "I am new to stock market. In current market and future potential give me 10-12 stocks "
    "I can invest for 10000 rupees and also how much to invest in each."
)

# message -> (intent, expected slots subset)
CASES = [
    (
        FAILING,
        "stock_list",
        {"amount_inr": 10000.0, "stock_count": 12, "stock_count_min": 10, "experience_level": "beginner"},
    ),
    ("what is an ETF", "education", {"concept": "ETF"}),
    ("explain SIP", "education", {"concept": "SIP"}),
    ("what is NAV", "education", {"concept": "NAV"}),
    ("should I buy TCS", "stock_single", {"symbol": "TCS"}),
    ("Suggest 10 stocks for ₹10,000", "stock_list", {"amount_inr": 10000.0, "stock_count": 10}),
    ("Plan a ₹5,000 monthly SIP", "plan_sip_fund", {"amount_inr": 5000.0, "amount_kind": "monthly"}),
    ("how is the market today", "market_overview", {}),
    ("what is the weather today", "off_topic", {}),
    ("who won the cricket match", "off_topic", {}),
    ("asdkj qwlkj zzz", "unclear", {}),
    ("I'm new, where do I start?", "unclear", {"experience_level": "beginner"}),
]


def _llm_json(intent: str, slots: dict) -> str:
    return json.dumps({"intent": intent, "slots": {k: v for k, v in slots.items() if k != "symbol"}})


@pytest.mark.parametrize(("message", "intent", "slots"), CASES)
async def test_rules_fallback(message, intent, slots, master):
    result = await extract(message, last_asked=None, has_prior_plan=False, master=master)
    assert result.source == "rules"
    assert result.intent == intent
    for name, value in slots.items():
        assert getattr(result.slots, name) == value


@pytest.mark.parametrize(("message", "intent", "slots"), CASES)
async def test_llm_path(message, intent, slots, use_llm, master):
    llm = use_llm(_llm_json(intent, slots))
    result = await extract(message, last_asked=None, has_prior_plan=False, master=master)
    assert result.source == "llm"
    assert llm.prompts
    assert result.intent == intent
    for name, value in slots.items():
        assert getattr(result.slots, name) == value


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '{"intent": "buy_everything", "slots": {}}',
        '{"intent": "education", "slots": {"horizon_years": -3}}',
    ],
)
async def test_invalid_llm_output_falls_back_to_rules(reply, use_llm, master):
    use_llm(reply)
    result = await extract("what is an ETF", last_asked=None, has_prior_plan=False, master=master)
    assert result.source == "rules"
    assert result.intent == "education"


async def test_llm_exception_falls_back_to_rules(use_llm, master):
    use_llm(RuntimeError("provider down"))
    result = await extract(FAILING, last_asked=None, has_prior_plan=False, master=master)
    assert result.source == "rules"
    assert result.intent == "stock_list"


async def test_llm_stock_single_cannot_swallow_a_stock_list_request(use_llm, master):
    """The original bug, reproduced through the model: it labelled the multi-stock request
    "stock". The rules know a count of stocks is a list, so the label is corrected."""
    use_llm(_llm_json("stock_single", {}))
    result = await extract(FAILING, last_asked=None, has_prior_plan=False, master=master)
    assert result.intent == "stock_list"


async def test_llm_invented_numbers_and_symbols_are_ignored(use_llm, master):
    use_llm(
        json.dumps(
            {
                "intent": "stock_list",
                "slots": {"amount_inr": 777777, "horizon_years": 9, "symbol": "FAKECO", "stock_count": 11},
            }
        )
    )
    result = await extract("suggest some stocks for me", last_asked=None, has_prior_plan=False, master=master)
    assert result.slots.amount_inr is None
    assert result.slots.horizon_years is None
    assert result.slots.stock_count is None
    assert result.slots.symbol is None


@pytest.mark.parametrize("word", ["OK", "yes", "NO", "ok", "Yes", "okay"])
async def test_filler_words_never_become_a_symbol(word, master):
    # "OK", "YES" and "NO" are even present in the fixture master as symbols.
    assert resolve_symbols(word, master).symbol is None
    result = await extract(word, last_asked=None, has_prior_plan=False, master=master)
    assert result.slots.symbol is None
    answered = await extract(word, last_asked="horizon_years", has_prior_plan=False, master=master)
    assert answered.intent == "answer"
    assert answered.slots.symbol is None


@pytest.mark.parametrize("message", ["I will buy ZZQX tomorrow", "ABCDEF looks good", "buy FAKECO"])
def test_unknown_all_caps_word_is_not_a_ticker(message, master):
    assert resolve_symbols(message, master).symbol is None


def test_symbols_resolve_by_exact_symbol_and_company_name(master):
    assert resolve_symbols("what about TCS?", master).symbol == "TCS"
    assert resolve_symbols("is tata consultancy a good buy", master).symbol == "TCS"
    assert resolve_symbols("should I buy infosys", master).symbol == "INFY"


def test_ambiguous_name_returns_candidates_not_a_symbol(master):
    match = resolve_symbols("tata", master)
    assert match.symbol is None
    assert {c["symbol"] for c in match.candidates} == {"TCS", "TATAMOTORS"}


def test_no_master_means_no_symbol():
    assert resolve_symbols("should I buy TCS", []).symbol is None


def test_search_universe_only_returns_real_entries(master):
    assert [e["symbol"] for e in search_universe("reliance", master)] == ["RELIANCE"]
    assert search_universe("zzzz", master) == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("₹10,000", {"amount_inr": 10000.0}),
        ("Rs 5000 per month", {"amount_inr": 5000.0, "amount_kind": "monthly"}),
        ("10k", {"amount_inr": 10000.0}),
        ("1.5 lakh lump sum", {"amount_inr": 150000.0, "amount_kind": "lump_sum"}),
        ("8 stocks for 20000 rupees", {"amount_inr": 20000.0, "stock_count": 8}),
        ("ten stocks", {"stock_count": 10}),
        ("10 to 12 shares", {"stock_count": 12, "stock_count_min": 10}),
        ("for 7 years", {"horizon_years": 7}),
        ("make it 8 stocks", {"stock_count": 8}),
        ("what about safer ones", {"risk_profile": "conservative"}),
        ("something riskier", {"risk_profile": "aggressive"}),
        ("just started investing", {"experience_level": "beginner"}),
        ("banking and pharma stocks", {"sectors_wanted": ["financial", "health"]}),
    ],
)
def test_slot_extraction(message, expected):
    slots = chat_intent.extract_slots(message)
    for name, value in expected.items():
        assert getattr(slots, name) == value


def test_year_count_is_not_read_as_an_amount():
    slots = chat_intent.extract_slots("I want to invest for 10 years with 25000 rupees")
    assert slots.amount_inr == 25000.0
    assert slots.horizon_years == 10


@pytest.mark.parametrize(
    ("last_asked", "reply", "field", "value"),
    [
        ("horizon_years", "5", "horizon_years", 5),
        ("amount", "5000", "amount_inr", 5000.0),
        ("risk_profile", "B", "risk_profile", "moderate"),
        ("risk_profile", "I don't know", "risk_profile", "moderate"),
        ("horizon_years", "not sure", "horizon_years", 5),
    ],
)
def test_terse_replies_are_read_in_context(last_asked, reply, field, value):
    assert getattr(chat_intent.extract_slots(reply, last_asked), field) == value


async def test_followup_tweak_is_an_answer_when_a_plan_exists(master):
    result = await extract("make it 8 stocks", last_asked=None, has_prior_plan=True, master=master)
    assert result.intent == "answer"
    assert result.slots.stock_count == 8
    safer = await extract("what about safer ones?", last_asked=None, has_prior_plan=True, master=master)
    assert safer.intent == "answer"
    assert safer.slots.risk_profile == "conservative"
