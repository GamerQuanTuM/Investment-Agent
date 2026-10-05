"""Bug 2: "I have 50000 rupees in capital" must be a one-time amount, never a monthly SIP.

Covers amount-kind detection, the one-question disambiguation, the lump-sum plan (named funds,
rupees, units, spread-over-months option), the fund-name label fix, beginner defaults and the
shared money formatter. The model is mocked or unavailable throughout."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from investment_agent.research import chat, sip
from investment_agent.research.chat_intent import extract_slots
from investment_agent.research.formatting import inr, normalize_money_text, pct

CAPITAL_MESSAGE = "I have 50000 rupees in capital and want to invest it in mutual funds"
BEGINNER_CAPITAL = "I am new. " + CAPITAL_MESSAGE

FUNDS = {
    "debt": ("100001", "Alpha Short Duration Fund - Direct Plan - Growth"),
    "large cap": ("100002", "Beta Bluechip Fund - Direct Plan - Growth"),
    "flexi cap": ("100003", "Gamma Flexi Cap Fund - Direct Plan - Growth"),
    "mid cap": ("100004", "Delta Midcap Fund - Direct Plan - Growth"),
    "small cap": ("100005", "Epsilon Smallcap Fund - Direct Plan - Growth"),
    "gold": ("100006", "Zeta Gold Fund - Direct Plan - Growth"),
}
WEIGHTS = {  # moderate profile
    "large cap": 40.0,
    "flexi cap": 30.0,
    "debt": 20.0,
    "gold": 10.0,
}


def _sid() -> str:
    return f"amt-{uuid.uuid4().hex[:8]}"


def _fund(category: str, amount: float, weight: float) -> dict[str, Any]:
    code, name = FUNDS[category]
    return {
        "scheme_code": code,
        "scheme_name": name,
        "amount_inr": amount,
        "weight_pct": weight,
        "latest_nav": 50.0,
        "nav_date": "2026-10-01",
        "units": round(amount / 50.0, 3),
        "return_3y_pct": 14.2,
        "return_5y_pct": 12.8,
        "source_name": "mfapi.in",
        "source_url": f"https://api.mfapi.in/mf/{code}",
    }


@pytest.fixture
def fake_plans(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    calls = SimpleNamespace(lump=[], mix=[])

    async def fake_lump(amount, horizon_years, risk_profile, return_span="quarter"):
        calls.lump.append((amount, horizon_years, risk_profile))
        sleeves = []
        for category, weight in WEIGHTS.items():
            piece = round(amount * weight / 100, 2)
            code, name = FUNDS[category]
            sleeves.append(
                {
                    "category": category,
                    "category_label": sip.CATEGORY_PLAIN_LABELS[category],
                    "weight_pct": weight,
                    "amount_inr": piece,
                    "status": "OK",
                    "scheme_code": code,
                    "scheme_name": name,
                    "funds": [_fund(category, piece, weight)],
                }
            )
        return {
            "mode": "lump_sum",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "amount_inr": amount,
            "allocated_inr": amount,
            "unallocated_inr": 0.0,
            "return_span_label": "this quarter",
            "sleeves": sleeves,
            "spread_option": sip.spread_option(amount, WEIGHTS),
            "note": "The first fund in each group had the best return.",
            "explanation": "This divides ₹50000.0 between 4 kinds of investment.",
        }

    async def fake_mix(monthly, horizon_years, risk_profile):
        calls.mix.append((monthly, horizon_years, risk_profile))
        sleeves = []
        for category, weight in WEIGHTS.items():
            code, name = FUNDS[category]
            sleeves.append(
                {
                    "category": category,
                    "category_label": sip.CATEGORY_PLAIN_LABELS[category],
                    "weight_pct": weight,
                    "monthly_inr": round(monthly * weight / 100, 2),
                    "status": "OK",
                    "scheme_code": code,
                    "scheme_name": name,
                    "trailing_return_pct_used": 3.2,
                    "return_window": "this quarter",
                }
            )
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": sleeves,
            "note": "n",
            "explanation": "Putting ₹5000.0 a month into these funds.",
        }

    monkeypatch.setattr(chat, "suggest_lump_sum", fake_lump)
    monkeypatch.setattr(chat, "suggest_mix", fake_mix)
    return calls


# ------------------------------------------------------------------ kind detection


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("I have 50000 rupees in capital", "lump_sum"),
        ("I have ₹2 lakh in savings", "lump_sum"),
        ("my corpus is 5 lakh rupees", "lump_sum"),
        ("I got a bonus of 80000 rupees", "lump_sum"),
        ("lump sum of 1 lakh", "lump_sum"),
        ("one-time 25000 rupees", "lump_sum"),
        ("invest 20000 now", "lump_sum"),
        ("₹5,000 per month", "monthly"),
        ("5000 rupees every month", "monthly"),
        ("a SIP of 3000", "monthly"),
        ("Plan a ₹5,000 monthly SIP", "monthly"),
        ("I have 50000 and want a monthly sip", "monthly"),
        ("invest 20000", None),
        ("20000 rupees", None),
    ],
)
def test_amount_kind_is_detected_never_assumed(message: str, kind: str | None):
    assert extract_slots(message).amount_kind == kind


def test_answer_chips_set_the_kind():
    assert extract_slots("One-time amount", "amount_kind").amount_kind == "lump_sum"
    assert extract_slots("Every month", "amount_kind").amount_kind == "monthly"


# --------------------------------------------------------------------- the bug report


@pytest.mark.parametrize("llm", ["rules", "mocked"])
async def test_capital_message_is_a_one_time_plan_with_named_funds(fake_plans, use_llm, llm):
    if llm == "mocked":
        use_llm(json.dumps({"intent": "plan_sip_fund", "slots": {"amount_inr": 50000, "amount_kind": "monthly"}}))
    result = await chat.chat_turn(_sid(), BEGINNER_CAPITAL)
    assert result["intent"] == "plan_sip_fund"
    assert result["collected"]["amount_kind"] == "lump_sum"  # rules beat a model that says monthly
    assert result["collected"]["monthly_amount"] is None
    assert fake_plans.lump == [(50000.0, 5, "moderate")] and not fake_plans.mix
    text = result["text"]
    assert "₹50,000 one-time" in text
    assert "/month" not in text and "per month" not in text
    assert text.count("a month") == 1  # only inside the clearly labelled spread-it-out option
    for _, name in (FUNDS[c] for c in WEIGHTS):
        assert name in text
    assert "₹20,000 (40%)" in text and "₹15,000 (30%)" in text  # rupees of the lump sum and weights
    assert "3y 14.2% a year" in text and "5y 12.8% a year" in text
    assert "about 400.000 units at NAV ₹50" in text
    assert "spread" in text.lower() and "12 months" in text and "₹4,167" in text
    assert "50000.0" not in text and "INR" not in text  # the model-written paragraph is normalised
    plan = result["plan"]
    assert plan["kind"] == "lump_sum" and plan["title"] == "₹50,000 one-time"
    assert "monthly_amount" not in plan and "/month" not in plan["title"]
    assert [r["scheme_name"] for r in plan["sleeves"]] == [FUNDS[c][1] for c in WEIGHTS]
    assert plan["spread_option"]["months"] == 12
    assert {s["source_name"] for s in result["sources"]} == {"mfapi.in (AMFI NAV data)"}
    assert all(s["data_date"] for s in result["sources"])


async def test_a_clear_amount_gets_a_plan_with_stated_defaults_not_two_questions(fake_plans):
    result = await chat.chat_turn(_sid(), CAPITAL_MESSAGE)
    assert result["needs_input"] is False and "one-time" in result["text"]
    assert "To get you started, I assumed 5 years and a balanced mix" in result["text"].replace("*", "")
    assert fake_plans.lump == [(50000.0, 5, "moderate")] and not fake_plans.mix


async def test_a_stated_horizon_still_gets_the_risk_question_never_monthly(fake_plans):
    session = _sid()
    first = await chat.chat_turn(session, CAPITAL_MESSAGE + " for 8 years")
    assert first["needs_input"] and "dropped" in first["text"].lower()  # the risk question
    done = await chat.chat_turn(session, "B")
    assert done["needs_input"] is False and "one-time" in done["text"]
    assert fake_plans.lump == [(50000.0, 8, "moderate")] and not fake_plans.mix


async def test_monthly_amount_stays_monthly_and_shows_fund_names(fake_plans):
    result = await chat.chat_turn(_sid(), "I am new. Plan a SIP of ₹5,000 per month")
    assert result["collected"]["amount_kind"] == "monthly"
    assert fake_plans.mix == [(5000.0, 5, "moderate")] and not fake_plans.lump
    text = result["text"]
    assert "₹5,000/month" in text and "one-time" not in text
    for category in WEIGHTS:
        assert FUNDS[category][1] in text  # the old `or`/`+` precedence bug dropped these
    assert "₹2,000 (40%)" in text and "3.2% over this quarter" in text
    assert "5000.0" not in text
    assert result["plan"]["kind"] == "monthly" and result["plan"]["title"] == "₹5,000/month"
    assert FUNDS["large cap"][1] in result["plan"]["sleeves"][0]["label"]
    assert result["plan"]["sleeves"][0]["scheme_name"] == FUNDS["large cap"][1]


async def test_a_category_without_a_fund_says_so_instead_of_inventing_one(monkeypatch: pytest.MonkeyPatch):
    async def mix(monthly, horizon_years, risk_profile):
        return {
            "mode": "suggest",
            "risk_profile": risk_profile,
            "horizon_years": horizon_years,
            "monthly_amount": monthly,
            "sleeves": [
                {
                    "category": "gold",
                    "category_label": sip.CATEGORY_PLAIN_LABELS["gold"],
                    "weight_pct": 100.0,
                    "monthly_inr": monthly,
                    "status": "DATA_UNAVAILABLE",
                    "scheme_code": None,
                    "scheme_name": None,
                    "funds": [],
                }
            ],
            "note": "n",
            "explanation": "e",
        }

    monkeypatch.setattr(chat, "suggest_mix", mix)
    result = await chat.chat_turn(_sid(), "I am new. Plan a SIP of ₹5,000 per month")
    assert "(no fund matched, data unavailable)" in result["text"]
    assert "sources" in result and result["sources"] == []


async def test_ambiguous_amount_asks_one_question_with_chips(fake_plans):
    session = _sid()
    first = await chat.chat_turn(session, "I am new. Invest 20000 in mutual funds for 5 years")
    assert first["needs_input"] is True
    assert "₹20,000" in first["text"] and "one-time" in first["text"] and "every month" in first["text"]
    assert first["suggestions"] == ["One-time amount", "Every month"]
    assert not fake_plans.lump and not fake_plans.mix  # nothing built before answering

    once = await chat.chat_turn(session, "One-time amount")
    assert once["needs_input"] is False and "₹20,000 one-time" in once["text"]
    assert fake_plans.lump and not fake_plans.mix


async def test_ambiguous_amount_answered_every_month_builds_a_monthly_plan(fake_plans):
    session = _sid()
    await chat.chat_turn(session, "I am new. Invest 20000 in mutual funds for 5 years")
    monthly = await chat.chat_turn(session, "Every month")
    assert monthly["needs_input"] is False
    assert "₹20,000/month" in monthly["text"] and fake_plans.mix and not fake_plans.lump


async def test_bare_amount_answer_to_the_monthly_question_is_monthly(fake_plans):
    session = _sid()
    await chat.chat_turn(session, "I want a SIP in mutual funds")
    await chat.chat_turn(session, "5")
    asked = await chat.chat_turn(session, "10000")
    assert asked["collected"]["amount_kind"] == "monthly" and asked["collected"]["monthly_amount"] == 10000.0


# -------------------------------------------------------------- beginner defaults


async def test_beginner_gets_defaults_stated_and_can_change_them_with_chips(fake_plans):
    session = _sid()
    result = await chat.chat_turn(session, "I am new. Plan a SIP of ₹5,000 per month")
    assert result["needs_input"] is False
    assert "I assumed 5 years and a balanced mix" in result["text"].replace("*", "")
    assert result["assumed"] == {"horizon_years": 5, "risk_profile": "moderate"}
    assert "What about 10 years?" in result["suggestions"]
    assert "What about a safer mix?" in result["suggestions"]

    longer = await chat.chat_turn(session, "What about 10 years?")
    assert longer["intent"] == "plan_sip_fund" and longer["needs_input"] is False
    assert fake_plans.mix[-1] == (5000.0, 10, "moderate")
    safer = await chat.chat_turn(session, "What about a safer mix?")
    assert fake_plans.mix[-1] == (5000.0, 10, "conservative")
    assert safer["needs_input"] is False


async def test_a_beginner_who_stated_the_horizon_is_not_second_guessed(fake_plans):
    result = await chat.chat_turn(_sid(), "I am new. Plan a SIP of ₹5,000 per month for 8 years")
    assert fake_plans.mix == [(5000.0, 8, "moderate")]
    plain = result["text"].replace("*", "")
    assert "I assumed a balanced mix" in plain and "years and" not in plain


# ----------------------------------------------------------------- ETF one-time


async def test_etf_plan_for_a_lump_sum_says_one_time(monkeypatch: pytest.MonkeyPatch):
    async def etf(amount, horizon_years, style):
        return {
            "mode": "etf",
            "style": style,
            "requested_style": style,
            "horizon_years": horizon_years,
            "monthly_amount": amount,
            "sleeves": [
                {"symbol": "NIFTYBEES", "label": "Large cap", "weight_pct": 100, "monthly_inr": amount,
                 "live_price": 250.0, "units": amount / 250.0}
            ],
            "note": "n",
        }

    monkeypatch.setattr(chat, "build_etf_sip", etf)
    result = await chat.chat_turn(_sid(), "I am new. I have 50000 rupees as one-time money, plan an ETF")
    assert result["intent"] == "plan_sip_etf"
    assert "₹50,000 one-time" in result["text"] and "a month" not in result["text"]
    assert result["plan"]["sleeves"][0]["amount_inr"] == 50000
    assert "monthly_inr" not in result["plan"]["sleeves"][0]


# ------------------------------------------------------ suggest_lump_sum (the maths)


def _history(latest: float = 50.0, years: int = 6, age_days: int = 1) -> list[dict[str, Any]]:
    start = datetime.now(UTC).date() - timedelta(days=age_days)
    days = years * 365
    return [{"date": (start - timedelta(days=d)).isoformat(), "nav": latest / (1.0003**d)} for d in range(days)]


def _pick(code: str, name: str, age_days: int = 1) -> dict[str, Any]:
    return {
        "scheme": SimpleNamespace(scheme_code=code, name=name),
        "history": {"nav_history": _history(age_days=age_days), "source_name": "mfapi.in", "source_url": f"https://api.mfapi.in/mf/{code}"},
        "score": 3.1,
        "annual_score": 12.0,
        "has_5y_history": True,
    }


async def test_suggest_lump_sum_amounts_units_and_spread(monkeypatch: pytest.MonkeyPatch):
    async def top(group: str, span_years: float, limit: int = 5):
        if group == "gold":
            return []  # no scorable gold fund
        code, name = FUNDS[group]
        return [_pick(code, name)]

    monkeypatch.setattr(sip, "_top_funds", top)
    result = await sip.suggest_lump_sum(100_000.0, 5, "moderate")
    by_cat = {s["category"]: s for s in result["sleeves"]}
    assert set(by_cat) == set(WEIGHTS)
    assert by_cat["large cap"]["amount_inr"] == 40_000.0 and by_cat["flexi cap"]["amount_inr"] == 30_000.0
    fund = by_cat["large cap"]["funds"][0]
    assert fund["units"] == pytest.approx(40_000.0 / 50.0, abs=0.001)
    assert fund["latest_nav"] == 50.0
    assert fund["nav_date"] == (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    assert fund["return_3y_pct"] == pytest.approx(((1.0003 ** (365 * 3)) ** (1 / 3) - 1) * 100, abs=0.5)
    assert fund["return_5y_pct"] is not None
    assert by_cat["gold"]["status"] == "DATA_UNAVAILABLE" and by_cat["gold"]["scheme_name"] is None
    assert result["allocated_inr"] == 90_000.0 and result["unallocated_inr"] == 10_000.0
    spread = result["spread_option"]
    assert spread["months"] == 12 and spread["monthly_inr"] == pytest.approx(100_000 / 12, abs=0.01)
    assert "₹1,00,000" in spread["note"] and "not advice" in spread["note"]
    assert "/month" not in result["explanation"]


async def test_suggest_lump_sum_never_names_a_dormant_or_non_growth_fund(monkeypatch: pytest.MonkeyPatch):
    async def top(group: str, span_years: float, limit: int = 5):
        code, name = FUNDS[group]
        return [
            _pick("900001", f"Old {name}", age_days=2000),  # best score, but no NAV for years
            _pick("900002", "Zed Large Cap Fund - Direct Plan - Bonus"),  # not the growth option
            _pick("900003", "Zed Large Cap Fund - Direct Plan - IDCW Payout"),
            _pick(code, name),
        ]

    monkeypatch.setattr(sip, "_top_funds", top)
    result = await sip.suggest_lump_sum(100_000.0, 5, "moderate")
    for sleeve in result["sleeves"]:
        assert [f["scheme_name"] for f in sleeve["funds"]] == [FUNDS[sleeve["category"]][1]]


def test_spread_months_follow_the_equity_share():
    assert sip.spread_option(120_000, {"large cap": 70.0, "debt": 30.0})["months"] == 12
    assert sip.spread_option(120_000, {"large cap": 45.0, "debt": 55.0})["months"] == 9
    conservative = sip.spread_option(120_000, {"debt": 60.0, "large cap": 30.0, "gold": 10.0})
    assert conservative["months"] == 6 and conservative["monthly_inr"] == 20_000.0


# ------------------------------------------------------------------ formatting


def test_inr_uses_indian_grouping_and_never_prints_dot_zero():
    assert inr(50_000) == "₹50,000"
    assert inr(20_000.0) == "₹20,000"
    assert inr(100_000) == "₹1,00,000"
    assert inr(2_500_000) == "₹25,00,000"
    assert inr(123_456_789) == "₹12,34,56,789"
    assert inr(1234.5) == "₹1,234.50"
    assert inr(318.55) == "₹318.55"
    assert inr(0) == "₹0"
    assert inr(-1500) == "-₹1,500"
    assert inr(None) == "—"
    assert "INR" not in inr(99) and ".0" not in inr(5000.0)


def test_pct_trims_trailing_zeros():
    assert pct(40.0) == "40%"
    assert pct(12.5) == "12.5%"
    assert pct(12.345) == "12.3%"
    assert pct(None) == "—"


def test_normalize_money_text_rewrites_every_spelling_and_keeps_punctuation():
    assert normalize_money_text("Put ₹20000.0 in, or INR 5000, or Rs. 1,00,000.") == (
        "Put ₹20,000 in, or ₹5,000, or ₹1,00,000."
    )
    assert normalize_money_text("pay ₹5,000, then wait") == "pay ₹5,000, then wait"
    assert normalize_money_text("no money here, only 12.5% growth") == "no money here, only 12.5% growth"


async def test_every_ranking_path_skips_dormant_and_non_growth_funds(monkeypatch: pytest.MonkeyPatch):
    """`_best_pick` feeds suggest_mix (monthly plans, the SIP page) and rank_funds too."""
    histories = {
        "1": ("Live Large Cap Fund - Direct Plan - Growth", 1),
        "2": ("Dead Large Cap Fund - Direct Plan - Growth", 2000),
        "3": ("Live Large Cap Fund - Direct Plan - Bonus", 1),
    }

    async def fetch(code: str):
        name, age = histories[code]
        return {"scheme_code": code, "scheme_name": name, "nav_history": _history(age_days=age)}

    monkeypatch.setattr(sip, "fetch_nav_history", fetch)
    picks = {code: await sip._best_pick(SimpleNamespace(scheme_code=code, name=histories[code][0])) for code in histories}
    assert picks["1"] is not None
    assert picks["2"] is None and picks["3"] is None
