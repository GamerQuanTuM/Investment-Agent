"""Chat that works for a total beginner and an experienced investor alike.

`chat_turn` is a small state machine around three pieces:

- `chat_intent.extract` turns the message into a validated intent + slots in one pass, so a
  message that already says "10-12 stocks for 10000 rupees" fills every slot at once and is
  never re-asked for what it gave. Symbols only ever come from the real security master.
- `chat_session` keeps the conversation (slots, pending question, last finished plan, last 6
  turns) in Redis with an in-memory fallback, so "make it 8 stocks" or "what about safer
  ones?" modifies the previous plan instead of restarting.
- One handler per intent. Every number a handler returns is computed in Python; models may
  only phrase or explain what the code already produced.

Every question accepts "I don't know" with a stated default and comes with quick-reply chips
(`suggestions`), and a terse numeric reply ("5", "5000") is read in the context of the
question that was just asked.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from investment_agent.market.universe import load_symbol_master
from investment_agent.research import chat_market, education, stock_list_chat
from investment_agent.research.chat_intent import Extraction, Slots, extract, search_universe
from investment_agent.research.chat_session import (
    add_turn,
    load_session,
    new_state,
    reset_session,
    save_session,
)
from investment_agent.research.evidence import Evidence, SourceType
from investment_agent.research.formatting import inr, normalize_money_text, pct
from investment_agent.research.guidance import guide_symbol
from investment_agent.research.sip import (
    CATEGORY_PLAIN_LABELS,
    build_etf_sip,
    rank_funds,
    suggest_lump_sum,
    suggest_mix,
)

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_YEARS = 5
DEFAULT_RISK_PROFILE = "moderate"

FLOW_INTENTS = ("stock_list", "stock_single", "plan_sip_fund", "plan_sip_etf")
SIP_FLOWS = ("plan_sip_fund", "plan_sip_etf")

# Plain-language framing for both the risk question's answer and the fund categories
# `suggest_mix` returns — a beginner should never see a bare "flexi cap"/"aggressive"
# without a sentence explaining what that actually means for their money.
_RISK_PLAIN_LABELS = {
    "conservative": "playing it safe (steadier, smaller ups and downs)",
    "moderate": "a balanced mix (some ups and downs for better long-term growth)",
    "aggressive": "higher risk (bigger swings for potentially higher long-term growth)",
}
_RISK_TO_ETF_CAP_STYLE = {"conservative": "large", "moderate": "flexi", "aggressive": "small"}

_RETRY_RE = re.compile(r"^(?:please\s+)?(?:try\s+again|retry)\s*[.!]*$", re.IGNORECASE)
_RESET_RE = re.compile(r"\b(start\s+over|start\s+again|reset|new\s+chat|clear\s+chat)\b", re.IGNORECASE)

OFF_TOPIC_MESSAGE = (
    "I can only help with the Indian stock market, mutual funds, SIPs and ETFs. "
    "That question doesn't look related — try one of the questions below."
)

STARTER_SUGGESTIONS = [
    "I'm new, where do I start?",
    "Suggest 10 stocks for ₹10,000",
    "What is an ETF?",
    "Plan a ₹5,000 monthly SIP",
]
OFF_TOPIC_SUGGESTIONS = [
    "Should I buy TCS for 5 years?",
    "What is a mutual fund?",
    "Plan a ₹5,000 monthly SIP",
]
_WELL_KNOWN_SYMBOLS = ("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC")

_QUESTION_CHIPS = {
    "horizon_years": ["3 years", "5 years", "10 years", "Not sure"],
    "amount": ["₹5,000", "₹10,000", "₹25,000"],
    "risk_profile": ["Play it safe", "Balanced mix", "Higher risk", "Not sure"],
    "amount_kind": ["One-time amount", "Every month"],
}
_ASSUMPTION_CHIPS = ["What about 10 years?", "What about a safer mix?", "What about higher risk?"]


# ------------------------------------------------------------------ response plumbing


def _collected_view(state: dict[str, Any]) -> dict[str, Any]:
    slots = state["slots"]
    flow = state.get("intent") or (state.get("last_result") or {}).get("intent")
    kind = slots.get("amount_kind")
    monthly = (
        slots.get("amount_inr")
        if kind == "monthly" or (kind != "lump_sum" and flow in ("plan_sip_fund", "plan_sip_etf", "stock_single"))
        else None
    )
    return {
        "intent": flow,
        "symbol": slots.get("symbol"),
        "horizon_years": slots.get("horizon_years"),
        "monthly_amount": monthly,
        "amount_inr": slots.get("amount_inr"),
        "amount_kind": slots.get("amount_kind"),
        "risk": slots.get("risk_profile"),
        "stock_count": slots.get("stock_count"),
        "experience_level": slots.get("experience_level"),
    }


def _body(text: str, *, needs_input: bool = False, suggestions: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {"text": text, "needs_input": needs_input, "suggestions": suggestions or [], **extra}


def _ask(state: dict[str, Any], field: str, text: str, chips: list[str] | None = None) -> dict[str, Any]:
    state["last_asked"] = field
    return _body(text, needs_input=True, suggestions=chips if chips is not None else _QUESTION_CHIPS.get(field, []))


# ------------------------------------------------------------------------- questions


def _next_question(flow: str, slots: dict[str, Any]) -> tuple[str, str] | None:
    if flow == "stock_single" and not slots.get("symbol"):
        return (
            "symbol",
            "Which company are you interested in? You can use its name or stock symbol, for example TCS or RELIANCE.",
        )
    if flow == "stock_list":
        if not slots.get("amount_inr"):
            return (
                "amount",
                "How much would you like to invest, in rupees? Just the number is fine, for example 10000.",
            )
        return None
    sip_flow = flow in SIP_FLOWS
    beginner_defaults = sip_flow and slots.get("experience_level") == "beginner"
    if slots.get("horizon_years") is None and not beginner_defaults:
        return (
            "horizon_years",
            (
                "How many years do you plan to stay invested before you might need this money? "
                "Just the number is fine (not sure? 5 years is a common starting point)."
            ),
        )
    if not slots.get("amount_inr"):
        if sip_flow and slots.get("amount_kind") == "lump_sum":
            return ("amount", "How much would you like to invest as a one-time amount, in rupees? For example 50000.")
        if sip_flow:
            return (
                "amount",
                (
                    "How much would you like to invest every month, in rupees? Just the number is fine, "
                    "for example 5000. (Investing a one-time amount instead? Say so, for example "
                    "\"one-time 50000\".)"
                ),
            )
        return ("amount", "How much can you invest, in rupees? Just the number is fine, for example 5000.")
    if sip_flow and slots.get("amount_kind") is None:
        return (
            "amount_kind",
            (
                f"Is {inr(slots['amount_inr'])} a one-time amount you want to invest now, "
                "or an amount you'll invest every month?"
            ),
        )
    if flow != "stock_single" and slots.get("risk_profile") is None and not beginner_defaults:
        return (
            "risk_profile",
            (
                "How would you feel if your investment's value dropped for a while before recovering?\n"
                "A) I'd rather play it safe — steadier investments, smaller ups and downs\n"
                "B) I'm okay with a balanced mix — some ups and downs for better long-term growth\n"
                "C) I'm fine with big swings for potentially higher long-term growth\n"
                "(Not sure? Most beginners pick B.)"
            ),
        )
    return None


# -------------------------------------------------------------------------- handlers


def _unclear_reply(ex: Extraction) -> dict[str, Any]:
    beginner = ex.slots.experience_level == "beginner"
    if beginner:
        text = (
            "Welcome, and good that you're starting early. Everyone begins somewhere. "
            "What would you like to do first?"
        )
    else:
        text = "I want to point you in the right direction. Which of these is closest to what you need?"
    return _body(text, needs_input=True, suggestions=list(STARTER_SUGGESTIONS if beginner else _unclear_chips(ex)))


def _unclear_chips(ex: Extraction) -> list[str]:
    amount = ex.slots.amount_inr
    shown = inr(amount) if amount else "₹10,000"
    plan_chip = (
        f"Invest {shown} one-time in mutual funds"
        if ex.slots.amount_kind == "lump_sum"
        else f"Plan a {shown} monthly SIP"
    )
    return [
        f"Suggest 10 stocks for {shown}",
        plan_chip,
        "What is an ETF?",
        "How is the market today?",
    ]


def _off_topic_reply() -> dict[str, Any]:
    return _body(OFF_TOPIC_MESSAGE, suggestions=list(OFF_TOPIC_SUGGESTIONS), error=True)


async def _symbol_question(
    state: dict[str, Any], ex: Extraction, master: list[dict[str, str]], message: str
) -> dict[str, Any]:
    candidates = ex.symbol_candidates[:5]
    if not master:
        return _body(
            "I can't look up companies right now because the market data is still loading. "
            "Please try again in a minute."
        )
    if not candidates:
        candidates = search_universe(message, master)
    if not candidates:
        known = {entry["symbol"]: entry for entry in master}
        candidates = [known[s] for s in _WELL_KNOWN_SYMBOLS if s in known][:4]
        lead = "I couldn't find that company in the NSE list I hold. Pick one of these, or type a company name:"
    else:
        lead = "I found more than one match. Which one do you mean?"
    state["symbol_candidates"] = candidates
    state["last_asked"] = "symbol"
    chips = [f"{c['symbol']} — {c['name']}" if c.get("name") else c["symbol"] for c in candidates]
    return _body(lead, needs_input=True, suggestions=chips)


async def _stock_single_reply(state: dict[str, Any]) -> dict[str, Any]:
    slots = state["slots"]
    try:
        guide = await guide_symbol(slots["symbol"], int(slots["horizon_years"]), float(slots["amount_inr"]))
    except Exception as exc:
        logger.info("Guidance unavailable for %s: %s", slots["symbol"], exc)
        return _body(
            f"DATA_UNAVAILABLE: I couldn't fetch live data for {slots['symbol']} right now, so I won't guess."
        )
    text = f"{guide['symbol']}: {guide['stance']}. {guide['summary']}"
    return _body(text, guidance=guide)


async def _ranked_funds_reply(state: dict[str, Any]) -> dict[str, Any]:
    slots = state["slots"]
    risk = slots.get("risk_profile") or DEFAULT_RISK_PROFILE
    years = int(slots.get("horizon_years") or DEFAULT_HORIZON_YEARS)
    rows = await rank_funds(risk, years)
    if not rows:
        text = "DATA_UNAVAILABLE: I couldn't find scored mutual funds right now — the fund master may not be synced yet."
    else:
        lines, current = [], None
        for row in rows:
            if row["category"] != current:
                current = row["category"]
                lines.append(f"\n{row['category_label'].capitalize()}:")
            lines.append(
                f"{row['rank']}. {row['scheme_name']} — {row['trailing_return_pct']:.1f}% a year ({row['return_window']})"
            )
        text = (
            f"Here are {len(rows)} funds for {_RISK_PLAIN_LABELS.get(risk, risk)} over {years} years, "
            "grouped by type and ranked by past yearly return (1 = strongest). Past returns don't "
            "guarantee future results — this isn't a recommendation." + "\n".join(lines)
        )
    return _body(text, ranking=rows)


def _is_lump(slots: dict[str, Any]) -> bool:
    return slots.get("amount_kind") == "lump_sum"


def _assume_beginner_defaults(slots: dict[str, Any]) -> list[str]:
    """A beginner who has not answered horizon/risk gets the safe defaults instead of two more
    questions. Returns what was assumed so the reply can say so."""
    assumed: list[str] = []
    if slots.get("experience_level") != "beginner":
        return assumed
    if slots.get("horizon_years") is None:
        slots["horizon_years"] = DEFAULT_HORIZON_YEARS
        assumed.append(f"{DEFAULT_HORIZON_YEARS} years")
    if slots.get("risk_profile") is None:
        slots["risk_profile"] = DEFAULT_RISK_PROFILE
        assumed.append("a balanced mix")
    return assumed


def _assumption_note(assumed: list[str]) -> str:
    return (
        f"Since you're new, I assumed {' and '.join(assumed)} to get you started. "
        "Tap an option below to change it."
    )


def _assumed_extra(assumed: list[str], slots: dict[str, Any]) -> dict[str, Any]:
    if not assumed:
        return {}
    return {
        "assumed": {"horizon_years": slots["horizon_years"], "risk_profile": slots["risk_profile"]},
    }


def _fund_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One source chip per shown fund (max 4): AMFI NAV data via mfapi.in, with the NAV date."""
    sources: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("scheme_name") or len(sources) >= 4:
            continue
        nav_date = row.get("nav_date")
        sources.append(
            Evidence(
                claim=f"NAV and returns for {row['scheme_name']}",
                source_name="mfapi.in (AMFI NAV data)",
                source_url=row.get("source_url") or "https://api.mfapi.in",
                source_type=SourceType.MFAPI,
                data_date=datetime.fromisoformat(nav_date).replace(tzinfo=UTC) if nav_date else None,
            ).model_dump(mode="json")
        )
    return sources


def _sleeve_label(category: str, plain: str | None, scheme_name: str | None) -> str:
    """"large, well-established companies — <fund name>", or an honest note when no fund exists.
    (Explicit variables: the old one-liner let `or` bind looser than `+`, dropping the name.)"""
    category_text = plain or CATEGORY_PLAIN_LABELS.get(category, category)
    if scheme_name:
        return f"{category_text} — {scheme_name}"
    return f"{category_text} (no fund matched, data unavailable)"


def _return_suffix(three_year: float | None, five_year: float | None) -> str:
    parts = []
    if three_year is not None:
        parts.append(f"3y {pct(three_year)} a year")
    if five_year is not None:
        parts.append(f"5y {pct(five_year)} a year")
    return f" · {', '.join(parts)}" if parts else ""


async def _etf_plan_reply(state: dict[str, Any]) -> dict[str, Any]:
    slots = state["slots"]
    assumed = _assume_beginner_defaults(slots)
    cap_style = _RISK_TO_ETF_CAP_STYLE.get(slots["risk_profile"], "flexi")
    plan = await build_etf_sip(float(slots["amount_inr"]), int(slots["horizon_years"]), cap_style)
    if _is_lump(slots):
        for row in plan["sleeves"]:
            row["amount_inr"] = row.pop("monthly_inr")
        plan["amount_inr"] = plan.pop("monthly_amount")
        plan["kind"] = "lump_sum"
        plan["title"] = f"{inr(plan['amount_inr'])} one-time"
        lines = [
            f"{row['label']} ({row['symbol']}): {inr(row['amount_inr'])} ({pct(row['weight_pct'])})"
            for row in plan["sleeves"]
        ]
        intro = (
            f"For {inr(plan['amount_inr'])} one-time over {plan['horizon_years']} years, here's a starting "
            "ETF mix (bought through your broker, a different mechanism from a mutual fund):\n"
        )
    else:
        plan["kind"] = "monthly"
        plan["title"] = f"{inr(plan['monthly_amount'])}/month"
        lines = [
            f"{row['label']} ({row['symbol']}): {inr(row['monthly_inr'])} ({pct(row['weight_pct'])})"
            for row in plan["sleeves"]
        ]
        intro = (
            f"For {inr(plan['monthly_amount'])} a month over {plan['horizon_years']} years, here's a starting "
            "ETF mix (bought through your broker — a different mechanism from a mutual fund SIP):\n"
        )
    text = intro + "\n".join(lines) + f"\n{plan['note']}"
    if assumed:
        text = f"{_assumption_note(assumed)}\n\n{text}"
    return _body(
        text,
        plan=plan,
        suggestions=list(_ASSUMPTION_CHIPS) if assumed else [],
        **_assumed_extra(assumed, slots),
    )


async def _lump_sum_fund_reply(state: dict[str, Any]) -> dict[str, Any]:
    """One-time amount: real mutual funds per category, in rupees (not a monthly SIP)."""
    slots = state["slots"]
    assumed = _assume_beginner_defaults(slots)
    amount = float(slots["amount_inr"])
    result = await suggest_lump_sum(amount, int(slots["horizon_years"]), slots["risk_profile"])
    rows: list[dict[str, Any]] = []
    for sleeve in result["sleeves"]:
        top = sleeve["funds"][0] if sleeve["funds"] else {}
        rows.append(
            {
                "symbol": sleeve.get("scheme_code") or sleeve["category"],
                "label": _sleeve_label(sleeve["category"], sleeve.get("category_label"), sleeve.get("scheme_name")),
                "category": sleeve["category"],
                "scheme_name": sleeve.get("scheme_name"),
                "weight_pct": sleeve["weight_pct"],
                "amount_inr": sleeve["amount_inr"],
                "units": top.get("units"),
                "latest_nav": top.get("latest_nav"),
                "nav_date": top.get("nav_date"),
                "return_3y_pct": top.get("return_3y_pct"),
                "return_5y_pct": top.get("return_5y_pct"),
                "source_url": top.get("source_url"),
            }
        )
    risk_label = _RISK_PLAIN_LABELS.get(result["risk_profile"], result["risk_profile"])
    plan = {
        "kind": "lump_sum",
        "title": f"{inr(amount)} one-time",
        "style": risk_label,
        "requested_style": result["risk_profile"],
        "horizon_years": result["horizon_years"],
        "amount_inr": amount,
        "note": result["note"],
        "sleeves": rows,
        "spread_option": result["spread_option"],
    }
    lines = []
    for row in rows:
        line = f"{row['label']}: {inr(row['amount_inr'])} ({pct(row['weight_pct'])})"
        if row["scheme_name"]:
            line += _return_suffix(row["return_3y_pct"], row["return_5y_pct"])
            if row["units"] is not None and row["latest_nav"] is not None:
                line += f" · about {row['units']:,.3f} units at NAV {inr(row['latest_nav'])} ({row['nav_date']})"
        lines.append(line)
    text = (
        f"For {inr(amount)} one-time over {result['horizon_years']} years, going with {risk_label}, "
        "here's a mutual fund mix:\n"
        + "\n".join(lines)
        + f"\n\n{result['spread_option']['note']}"
        + f"\n\n{normalize_money_text(result['explanation'])}\n{result['note']}"
    )
    if assumed:
        text = f"{_assumption_note(assumed)}\n\n{text}"
    suggestions = [*(_ASSUMPTION_CHIPS if assumed else []), "What is NAV?"]
    return _body(
        text,
        plan=plan,
        sources=_fund_sources(rows),
        suggestions=suggestions,
        **_assumed_extra(assumed, slots),
    )


async def _fund_plan_reply(state: dict[str, Any]) -> dict[str, Any]:
    """Default SIP path: real mutual funds (`suggest_mix`), not ETFs. A one-time amount gets its
    own lump-sum plan instead of being passed off as a monthly SIP."""
    if _is_lump(state["slots"]):
        return await _lump_sum_fund_reply(state)
    slots = state["slots"]
    assumed = _assume_beginner_defaults(slots)
    result = await suggest_mix(slots["amount_inr"], slots["horizon_years"], slots["risk_profile"])
    sleeves = []
    for sleeve in result["sleeves"]:
        sleeves.append(
            {
                "symbol": sleeve.get("scheme_code") or "—",
                "label": _sleeve_label(sleeve["category"], sleeve.get("category_label"), sleeve.get("scheme_name")),
                "scheme_name": sleeve.get("scheme_name"),
                "weight_pct": sleeve["weight_pct"],
                "monthly_inr": sleeve["monthly_inr"],
                "return_pct": sleeve.get("trailing_return_pct_used"),
                "return_window": sleeve.get("return_window"),
            }
        )
    risk_label = _RISK_PLAIN_LABELS.get(result["risk_profile"], result["risk_profile"])
    plan = {
        "kind": "monthly",
        "title": f"{inr(result['monthly_amount'])}/month",
        "style": risk_label,
        "requested_style": result["risk_profile"],
        "horizon_years": result["horizon_years"],
        "monthly_amount": result["monthly_amount"],
        "note": result["note"],
        "sleeves": sleeves,
    }
    lines = []
    for row in sleeves:
        line = f"{row['label']}: {inr(row['monthly_inr'])} ({pct(row['weight_pct'])})"
        if row["scheme_name"] and row["return_pct"] is not None and row["return_window"]:
            line += f" · {pct(row['return_pct'])} over {row['return_window']}"
        lines.append(line)
    text = (
        f"For {inr(result['monthly_amount'])}/month over {result['horizon_years']} years, going with {risk_label}, "
        "here's a mutual fund mix:\n"
        + "\n".join(lines)
        + f"\n\n{normalize_money_text(result['explanation'])}"
    )
    if assumed:
        text = f"{_assumption_note(assumed)}\n\n{text}"
    extra: dict[str, Any] = _assumed_extra(assumed, slots)
    if any(row["scheme_name"] for row in sleeves):
        extra["sources"] = _fund_sources(sleeves)
    return _body(text, plan=plan, suggestions=list(_ASSUMPTION_CHIPS) if assumed else [], **extra)


# ---------------------------------------------------------------------------- engine


def _start_flow(state: dict[str, Any], ex: Extraction) -> None:
    """Begin a new request: fresh slots, keeping only who the user said they are. Planning a
    SIP right after a stock list reuses its amount, horizon and risk (the 'index fund
    instead?' hop) because the user never restated them."""
    carried: dict[str, Any] = {}
    if state["slots"].get("experience_level"):
        carried["experience_level"] = state["slots"]["experience_level"]
    last = state.get("last_result")
    if ex.intent in ("plan_sip_fund", "plan_sip_etf") and last and last["intent"] == "stock_list":
        previous = last["slots"]
        defaults = last.get("defaults", {})
        for name in ("amount_inr", "horizon_years", "risk_profile"):
            if previous.get(name) or defaults.get(name):
                carried[name] = previous.get(name) or defaults[name]
        carried["amount_kind"] = "monthly"
    state["slots"] = carried
    state["intent"] = ex.intent
    state["last_asked"] = None
    state["symbol_candidates"] = []


def _apply_slots(state: dict[str, Any], ex: Extraction) -> None:
    provided = ex.slots.provided()
    provided.pop("concept", None)
    provided.pop("term_a", None)
    provided.pop("term_b", None)
    # A bare number typed in answer to "how much every month?" is the monthly amount.
    answering_monthly = state.get("last_asked") == "amount" and state.get("intent") in SIP_FLOWS
    state["slots"].update(provided)
    if answering_monthly and "amount_inr" in provided and not state["slots"].get("amount_kind"):
        state["slots"]["amount_kind"] = "monthly"


async def _run_flow(
    state: dict[str, Any], ex: Extraction, master: list[dict[str, str]], message: str
) -> dict[str, Any]:
    flow = state["intent"]
    slots = state["slots"]
    question = _next_question(flow, slots)
    if question:
        field, text = question
        if field == "symbol":
            return await _symbol_question(state, ex, master, message)
        return _ask(state, field, text)

    if flow == "stock_single":
        body = await _stock_single_reply(state)
    elif flow == "plan_sip_etf":
        body = await _etf_plan_reply(state)
    elif flow == "stock_list":
        body = await stock_list_chat.stock_list_reply(slots)
    else:
        body = await _fund_plan_reply(state)
    state["last_result"] = {
        "intent": flow,
        "slots": dict(slots),
        "defaults": body.pop("plan_defaults", {}),
    }
    # A reply that said "loading, try again" remembers what to re-run when the chip is tapped.
    state["retry"] = {"intent": flow, "slots": dict(slots)} if body.pop("retry", False) else None
    state["intent"] = None
    state["last_asked"] = None
    return body


async def _dispatch(
    state: dict[str, Any], ex: Extraction, message: str, master: list[dict[str, str]]
) -> tuple[str, dict[str, Any]]:
    intent = ex.intent
    last = state.get("last_result")
    if (
        intent == "answer"
        and not state["intent"]
        and ex.slots.stock_count
        and not (last and last["intent"] == "stock_list")
    ):
        intent = "stock_list"  # "make it 8 stocks" after a non-stock plan is a new list request
    if intent == "answer":
        if state["intent"]:
            pass  # keep filling the open flow
        elif state.get("last_result"):
            # A tweak ("make it 8 stocks", "safer ones?") reopens the last finished plan.
            state["intent"] = state["last_result"]["intent"]
            state["slots"] = dict(state["last_result"]["slots"])
        else:
            intent = "unclear"
    elif intent in FLOW_INTENTS:
        _start_flow(state, ex)
    if intent == "answer":
        flow = state["intent"]
        if state["last_asked"] == "symbol" and not ex.slots.symbol:
            ex = ex.model_copy(update={"symbol_candidates": state.get("symbol_candidates", [])})
        _apply_slots(state, ex)
        return flow, await _run_flow(state, ex, master, message)
    if intent in FLOW_INTENTS:
        _apply_slots(state, ex)
        return intent, await _run_flow(state, ex, master, message)

    if intent == "off_topic":
        return intent, _off_topic_reply()
    if intent == "fund_list":
        _apply_slots(state, ex)
        return intent, await _ranked_funds_reply(state)
    if intent == "education":
        amount = state["slots"].get("amount_inr") or ex.slots.amount_inr
        answer = await education.explain(message, ex.slots.concept, amount)
        return intent, _body(
            answer["text"],
            suggestions=answer["suggestions"],
            sources=answer["sources"],
            **({"glossary": answer["glossary"]} if "glossary" in answer else {}),
        )
    if intent == "compare":
        answer = await education.compare(message, ex.slots.term_a, ex.slots.term_b)
        return intent, _body(
            answer["text"],
            suggestions=answer["suggestions"],
            sources=answer["sources"],
            **({"comparison": answer["comparison"]} if "comparison" in answer else {}),
        )
    if intent == "market_overview":
        return intent, await chat_market.market_overview_reply()
    if intent == "portfolio_help":
        return intent, await chat_market.portfolio_help_reply()
    return "unclear", _unclear_reply(ex)


async def chat_turn(session_id: str, message: str) -> dict[str, Any]:
    message = message.strip()
    if _RESET_RE.search(message):
        state = await reset_session(session_id)
        body = _body(
            "Starting fresh. What would you like to do?",
            needs_input=True,
            suggestions=list(STARTER_SUGGESTIONS),
        )
        return {"session_id": session_id, "intent": None, "collected": _collected_view(state), "sources": [], **body}

    state = await load_session(session_id)
    master = await load_symbol_master()
    pending_retry = state.get("retry")
    state["retry"] = None
    if pending_retry and _RETRY_RE.match(message):
        state["intent"] = pending_retry["intent"]
        state["slots"] = dict(pending_retry["slots"])
        retry_ex = Extraction(intent=pending_retry["intent"], slots=Slots())
        body = await _run_flow(state, retry_ex, master, message)
        add_turn(state, message, body["text"])
        await save_session(session_id, state)
        return {
            "session_id": session_id,
            "intent": pending_retry["intent"],
            "collected": _collected_view(state),
            "sources": [],
            **body,
        }
    ex = await extract(
        message,
        last_asked=state["last_asked"],
        has_prior_plan=state.get("last_result") is not None or state["intent"] is not None,
        master=master,
    )
    intent, body = await _dispatch(state, ex, message, master)
    add_turn(state, message, body["text"])
    await save_session(session_id, state)
    return {
        "session_id": session_id,
        "intent": intent,
        "collected": _collected_view(state),
        "sources": [],
        **body,
    }


__all__ = ["OFF_TOPIC_MESSAGE", "chat_turn", "new_state"]
