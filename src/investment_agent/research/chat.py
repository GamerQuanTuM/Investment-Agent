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
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from investment_agent.market.universe import load_symbol_master
from investment_agent.research import (
    chat_ai,
    chat_guardrails,
    chat_market,
    chat_memory,
    consultant,
    education,
    progress,
    stock_list_chat,
)
from investment_agent.research.chat_intent import (
    _OFF_TOPIC_RE,
    Extraction,
    Slots,
    extract,
    search_universe,
)
from investment_agent.research.chat_memory import conversation_context
from investment_agent.research.chat_session import (
    add_turn,
    load_session,
    new_state,
    reset_session,
    save_session,
)
from investment_agent.research.evidence import Evidence, SourceType
from investment_agent.research.formatting import inr, normalize_money_text, pct
from investment_agent.research.glossary import asks_for_definition
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
_YES_RE = re.compile(
    r"^(?:yes|yeah|yep|y|sure|ok(?:ay)?|continue|go ahead|proceed|please do)(?:[,.!\s]+(?:continue|go ahead|please))?\W*$",
    re.IGNORECASE,
)
_NO_RE = re.compile(r"^(?:no|nope|n|stop|cancel|not now|no thanks)(?:[,.!\s]+(?:stop|thanks))?\W*$", re.IGNORECASE)
CONFIRM_CHIPS = ["Yes, continue", "No, stop"]
CONFIRM_TEXT = (
    "### Before I answer\n\n"
    "This sounds like money that matters a lot to you, so I want to be careful.\n\n"
    "- I can only share **general education**, not personal advice.\n"
    "- *No one can promise an outcome*, and investments can lose value.\n"
    "- If you may need this money soon, **protecting it usually matters more than growing it**.\n\n"
    "Would you like me to continue with general information?"
)
STOP_TEXT = (
    "Okay, I've stopped here. Whenever you're ready, I'm happy to explain something general, such as how "
    "risk works or how to spread money across investments. For decisions about your own money, a "
    "SEBI-registered adviser can look at your whole situation."
)
_RESET_RE = re.compile(r"\b(start\s+over|start\s+again|reset|new\s+chat|clear\s+chat)\b", re.IGNORECASE)

OFF_TOPIC_MESSAGE = (
    "I only answer questions about stocks and the Indian market (including mutual funds, SIPs and "
    "ETFs). That question doesn't look related, so I'll leave it. Try one of the questions below."
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
    if sip_flow and slots.get("amount_inr") and slots.get("amount_kind") is None:
        return (
            "amount_kind",
            (
                f"Is {inr(slots['amount_inr'])} a one-time amount you want to invest now, "
                "or an amount you'll invest every month?"
            ),
        )
    beginner_defaults = sip_flow and _uses_defaults(slots)
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
    progress.emit("data", f"Fetching live price and fundamentals for {slots['symbol']}")
    try:
        guide = await guide_symbol(slots["symbol"], int(slots["horizon_years"]), float(slots["amount_inr"]))
    except Exception as exc:
        logger.info("Guidance unavailable for %s: %s", slots["symbol"], exc)
        return _body(
            f"DATA_UNAVAILABLE: I couldn't fetch live data for {slots['symbol']} right now, so I won't guess."
        )
    text = f"{guide['symbol']}: {guide['stance']}. {guide['summary']}"
    row = {"symbol": guide["symbol"], "name": guide.get("name") or guide["symbol"], "sector": guide.get("sector") or "its sector"}
    progress.emit("data", f"Fetched live data for {slots['symbol']}", done=True)
    research = await consultant.research_stocks([row])
    notes = consultant.render([row], research)
    if notes:
        text = f"{text}\n\n{notes}"
    return _body(text, guidance=guide, sources=research.get("sources", []))


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


def _uses_defaults(slots: dict[str, Any]) -> bool:
    """Skip the horizon and risk questions: for a beginner, and for anyone who already gave a
    clear amount (and whether it is one-time or monthly) without saying anything else."""
    if slots.get("experience_level") == "beginner":
        return True
    return bool(
        slots.get("amount_inr")
        and slots.get("amount_kind")
        and slots.get("horizon_years") is None
        and slots.get("risk_profile") is None
    )


def _assume_beginner_defaults(slots: dict[str, Any]) -> list[str]:
    """When `_uses_defaults`, fill horizon/risk with the safe defaults instead of asking two more
    questions. Returns what was assumed so the reply can say so."""
    assumed: list[str] = []
    if not _uses_defaults(slots):
        return assumed
    if slots.get("horizon_years") is None:
        slots["horizon_years"] = DEFAULT_HORIZON_YEARS
        assumed.append(f"{DEFAULT_HORIZON_YEARS} years")
    if slots.get("risk_profile") is None:
        slots["risk_profile"] = DEFAULT_RISK_PROFILE
        assumed.append("a balanced mix")
    return assumed


def _assumption_note(assumed: list[str], slots: dict[str, Any]) -> str:
    lead = "Since you're new, I" if slots.get("experience_level") == "beginner" else "To get you started, I"
    return f"*{lead} assumed **{' and '.join(assumed)}**. Tap an option below to change it.*"


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
            f"- **{row['label']}** ({row['symbol']}): {inr(row['amount_inr'])} ({pct(row['weight_pct'])})"
            for row in plan["sleeves"]
        ]
        intro = (
            f"For **{inr(plan['amount_inr'])} one-time** over {plan['horizon_years']} years, here's a starting "
            "ETF mix (bought through your broker, a different mechanism from a mutual fund):\n\n"
        )
    else:
        plan["kind"] = "monthly"
        plan["title"] = f"{inr(plan['monthly_amount'])}/month"
        lines = [
            f"- **{row['label']}** ({row['symbol']}): {inr(row['monthly_inr'])} ({pct(row['weight_pct'])})"
            for row in plan["sleeves"]
        ]
        intro = (
            f"For **{inr(plan['monthly_amount'])} a month** over {plan['horizon_years']} years, here's a starting "
            "ETF mix (bought through your broker — a different mechanism from a mutual fund SIP):\n\n"
        )
    text = intro + "\n".join(lines) + f"\n\n*{plan['note']}*"
    if assumed:
        text = f"{_assumption_note(assumed, slots)}\n\n{text}"
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
        line = f"- **{row['label']}**: {inr(row['amount_inr'])} ({pct(row['weight_pct'])})"
        if row["scheme_name"]:
            line += _return_suffix(row["return_3y_pct"], row["return_5y_pct"])
            if row["units"] is not None and row["latest_nav"] is not None:
                line += f" · about {row['units']:,.3f} units at NAV {inr(row['latest_nav'])} ({row['nav_date']})"
        lines.append(line)
    text = (
        f"For **{inr(amount)} one-time** over {result['horizon_years']} years, going with {risk_label}, "
        "here's a mutual fund mix:\n\n"
        + "\n".join(lines)
        + f"\n\n> {result['spread_option']['note']}"
        + f"\n\n{normalize_money_text(result['explanation'])}\n\n*{result['note']}*"
    )
    if assumed:
        text = f"{_assumption_note(assumed, slots)}\n\n{text}"
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
        line = f"- **{row['label']}**: {inr(row['monthly_inr'])} ({pct(row['weight_pct'])})"
        if row["scheme_name"] and row["return_pct"] is not None and row["return_window"]:
            line += f" · {pct(row['return_pct'])} over {row['return_window']}"
        lines.append(line)
    text = (
        f"For **{inr(result['monthly_amount'])}/month** over {result['horizon_years']} years, going with {risk_label}, "
        "here's a mutual fund mix:\n\n"
        + "\n".join(lines)
        + f"\n\n{normalize_money_text(result['explanation'])}"
    )
    if assumed:
        text = f"{_assumption_note(assumed, slots)}\n\n{text}"
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
        previous = (state.get("last_result") or {}).get("shown") if state.get("last_result") else None
        body = await stock_list_chat.stock_list_reply(slots, previous=previous)
    else:
        body = await _fund_plan_reply(state)
    shown = [r["symbol"] for r in (body.get("stock_plan") or {}).get("rows", [])]
    slots.pop("exclude_symbols", None)  # applies to this one list only, not to later tweaks
    state["last_result"] = {
        "intent": flow,
        "shown": shown,
        "slots": dict(slots),
        "defaults": body.pop("plan_defaults", {}),
    }
    # A reply that said "loading, try again" remembers what to re-run when the chip is tapped.
    state["retry"] = {"intent": flow, "slots": dict(slots)} if body.pop("retry", False) else None
    state["intent"] = None
    state["last_asked"] = None
    return body


# True while the user has the Research toggle on: concept, comparison, market and unclear
# questions are then answered from live web sources only, and anything off-topic is declined.
research_mode: ContextVar[bool] = ContextVar("research_mode", default=False)
_RESEARCHABLE = frozenset({"education", "compare", "market_overview", "unclear"})
NO_SEARCH_TEXT = (
    "Research mode needs web search, which isn't set up on this server yet "
    "(add TAVILY_API_KEY). You can switch Research off to get a general answer."
)
NO_SOURCES_TEXT = (
    "I couldn't find reliable recent sources for that, so I won't guess. "
    "Try rewording it, naming the company or topic, or switch Research off for a general explanation."
)


async def _research_reply(intent: str, message: str) -> tuple[str, dict[str, Any]] | None:
    """A cited web-research answer, or None to carry on with the normal answer path."""
    forced = research_mode.get()
    if intent not in _RESEARCHABLE or not (
        forced or (intent == "education" and consultant.needs_fresh_facts(message))
    ):
        return None
    result = await consultant.research_answer(message, conversation_context.get())
    if result["status"] == "OK":
        return intent, _body(
            result["text"],
            suggestions=["What are the risks?", "Suggest 10 stocks for ₹10,000", "What is an ETF?"],
            sources=result["sources"],
            answered_by="ai" if result["written_by"] == "ai" else "reviewed",
            research={"tools_used": result["tools_used"], "mode": "forced" if forced else "auto"},
        )
    if result["status"] == "OUT_OF_SCOPE":
        return "off_topic", _off_topic_reply()
    if not forced:
        return None  # automatic search failed: the normal answer is still fine
    text = NO_SEARCH_TEXT if result.get("reason") == "no_key" else NO_SOURCES_TEXT
    return intent, _body(text, suggestions=list(STARTER_SUGGESTIONS))


_MORE_RE = re.compile(r"\b(more|another|additional|extra|other|different)\b", re.IGNORECASE)
_MORE_CHIP = "{n} more, different from these"
_TOTAL_CHIP = "A fresh list of {n} in total"


def _needs_more_clarification(state: dict[str, Any], ex: Extraction, message: str, intent: str) -> bool:
    """"More 20 stocks" after a finished list could mean 20 extra or 20 in total: ask which."""
    last = state.get("last_result")
    return bool(
        last
        and last["intent"] == "stock_list"
        and last.get("shown")
        and ex.slots.stock_count
        and intent in ("stock_list", "answer")
        and _MORE_RE.search(message)
    )


def _more_question(state: dict[str, Any], ex: Extraction, message: str) -> dict[str, Any]:
    n = int(ex.slots.stock_count or 0)
    shown = state["last_result"]["shown"]
    state["clarify"] = {"kind": "more_stocks", "count": n}
    return _body(
        f"Quick check so I get this right: do you want **{n} more stocks** on top of the "
        f"{len(shown)} I already showed (all different from those), or **a fresh list of {n} in total**?",
        needs_input=True,
        suggestions=[_MORE_CHIP.format(n=n), _TOTAL_CHIP.format(n=n)],
    )


async def _answer_more_question(
    session_id: str, state: dict[str, Any], message: str, pending: dict[str, Any], master: list[dict[str, str]]
) -> dict[str, Any] | None:
    """Run the list the person chose; None if their reply was something else entirely."""
    n = pending["count"]
    wants_more = message.strip().lower().startswith(_MORE_CHIP.format(n=n).lower()[:12]) or bool(
        re.search(r"\b(more|different|additional|extra|on top)\b", message, re.IGNORECASE)
    )
    wants_total = bool(re.search(r"\b(fresh|total|new list|in all|altogether)\b", message, re.IGNORECASE))
    if not (wants_more or wants_total):
        return None
    last = state["last_result"]
    state["intent"] = "stock_list"
    state["slots"] = {**last["slots"], "stock_count": n}
    if wants_total:
        state["slots"].pop("exclude_symbols", None)
    else:
        state["slots"]["exclude_symbols"] = list(last["shown"])
    body = await _run_flow(state, Extraction(intent="stock_list", slots=Slots()), master, message)
    await _finish_turn(session_id, state, message, body["text"])
    return {
        "session_id": session_id,
        "intent": "stock_list",
        "collected": _collected_view(state),
        "sources": [],
        **body,
    }


_PENNY_RE = re.compile(r"\b(penny|cheap(?:est)? stocks?|low[- ]?priced|multibagger)\b", re.IGNORECASE)
_PRICE_UNDER_RE = re.compile(r"\b(?:under|below|less than|upto|up to|within)\s*(?:rs\.?|inr|₹)?\s*(\d{1,4})\b", re.IGNORECASE)
_PENNY_PRICES = (10, 20)  # what people usually mean by a penny stock: a share under Rs 10-20
_PENNY_SMALL_CHIP = "Include smaller companies (riskier)"
_PENNY_SAFE_CHIP = "Keep the usual safer list"


def _penny_chips() -> list[str]:
    return [*(f"Under ₹{p} a share" for p in _PENNY_PRICES), _PENNY_SMALL_CHIP, _PENNY_SAFE_CHIP]


def _needs_penny_question(state: dict[str, Any], message: str, intent: str) -> bool:
    return intent == "stock_list" and bool(_PENNY_RE.search(message)) and "penny_choice" not in state["slots"]


def _penny_question(state: dict[str, Any], ex: Extraction) -> dict[str, Any]:
    state["clarify"] = {"kind": "penny", "slots": ex.slots.model_dump(exclude_none=True)}
    return _body(
        "Quick check: what share price counts as \"penny\" for you? Most people mean a share priced under "
        "₹10-20. Those are usually small or struggling companies that trade thinly and can swing "
        "wildly, so my normal list leaves them out, but I can search for them and show the risks.",
        needs_input=True,
        suggestions=_penny_chips(),
    )


def _penny_choice(message: str) -> tuple[str, int | None] | None:
    """(choice, price cap) from the person's reply, or None if it was something else."""
    lowered = message.lower()
    price = _PRICE_UNDER_RE.search(message)
    if price:
        return "price", int(price.group(1))
    if "smaller" in lowered or "riskier" in lowered:
        return "small", None
    if "safer" in lowered or "usual" in lowered or "keep" in lowered:
        return "safe", None
    return None


async def _run_penny_flow(
    state: dict[str, Any], saved: dict[str, Any], choice: str, cap: int | None, master: list[dict[str, str]], message: str
) -> dict[str, Any]:
    ex = Extraction(intent="stock_list", slots=Slots(**saved))
    _start_flow(state, ex)
    _apply_slots(state, ex)
    state["slots"]["penny_choice"] = choice
    if choice == "price":
        # A real penny search has to look at small companies, so the size floor is lowered too.
        state["slots"]["price_cap"] = cap
        state["slots"]["include_small"] = True
    elif choice == "small":
        state["slots"]["include_small"] = True
    return await _run_flow(state, ex, master, message)


async def _answer_penny_question(
    session_id: str, state: dict[str, Any], message: str, pending: dict[str, Any], master: list[dict[str, str]]
) -> dict[str, Any] | None:
    picked = _penny_choice(message)
    if picked is None:
        return None
    body = await _run_penny_flow(state, pending["slots"], picked[0], picked[1], master, message)
    await _finish_turn(session_id, state, message, body["text"])
    return {
        "session_id": session_id,
        "intent": "stock_list",
        "collected": _collected_view(state),
        "sources": [],
        **body,
    }


_NO_CROSS_QUESTION = frozenset({"answer", "off_topic", "guardrail"})


def _model_question(state: dict[str, Any], ex: Extraction, message: str) -> dict[str, Any] | None:
    """The model's own clarifying question, when it judged the message ambiguous. Asked at most
    once per request, only if the text passes the safety check, and never in place of the
    deterministic "N more stocks" question."""
    if (
        not ex.clarify
        or ex.source != "llm"
        or ex.intent in _NO_CROSS_QUESTION
        or _needs_more_clarification(state, ex, message, ex.intent)
        or not chat_ai.passes_ai_check(ex.clarify)
    ):
        return None
    options = [o.strip() for o in ex.clarify_options if o.strip() and len(o) <= 70 and chat_ai.passes_ai_check(o)]
    logger.info("Cross-question: the model asked for clarification (intent=%s)", ex.intent)
    return _body(ex.clarify.strip(), needs_input=True, suggestions=options[:3] or list(STARTER_SUGGESTIONS))


async def _dispatch(
    state: dict[str, Any], ex: Extraction, message: str, master: list[dict[str, str]]
) -> tuple[str, dict[str, Any]]:
    intent = ex.intent
    if _needs_more_clarification(state, ex, message, intent):
        return "stock_list", _more_question(state, ex, message)
    if _needs_penny_question(state, message, intent):
        stated = _PRICE_UNDER_RE.search(message)
        if stated:
            body = await _run_penny_flow(
                state, ex.slots.model_dump(exclude_none=True), "price", int(stated.group(1)), master, message
            )
            return "stock_list", body
        return "stock_list", _penny_question(state, ex)
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
    researched = await _research_reply(intent, message)
    if researched is not None:
        return researched
    if intent == "fund_list":
        _apply_slots(state, ex)
        return intent, await _ranked_funds_reply(state)
    if intent == "guardrail":
        stance = await chat_guardrails.reply(message)
        return intent, _body(
            stance["text"],
            suggestions=stance["suggestions"],
            guardrail=stance["kind"],
            answered_by=stance["answered_by"],
        )
    if intent == "education":
        amount = state["slots"].get("amount_inr") or ex.slots.amount_inr
        answer = await education.explain(message, ex.slots.concept, amount)
        extra: dict[str, Any] = {"glossary": answer["glossary"]} if "glossary" in answer else {}
        extra["answered_by"] = answer.get("answered_by", "reviewed")
        if _OFF_TOPIC_RE.search(message):  # "capital of France, also what is NAV?"
            extra["notice"] = "I can only help with investing, so I've answered just that part."
        return intent, _body(
            answer["text"], suggestions=answer["suggestions"], sources=answer["sources"], **extra
        )
    if intent == "compare":
        answer = await education.compare(message, ex.slots.term_a, ex.slots.term_b)
        return intent, _body(
            answer["text"],
            suggestions=answer["suggestions"],
            sources=answer["sources"],
            answered_by=answer.get("answered_by", "ai"),
            **({"comparison": answer["comparison"]} if "comparison" in answer else {}),
        )
    if intent == "market_overview":
        return intent, await chat_market.market_overview_reply()
    if intent == "portfolio_help":
        return intent, await chat_market.portfolio_help_reply()
    reply = _unclear_reply(ex)
    asked = await chat_ai.write(chat_ai.TASKS["clarify"], message, reference=reply["text"])
    if asked:
        reply["text"] = asked
    return "unclear", reply


async def _finish_turn(session_id: str, state: dict[str, Any], message: str, reply: str) -> None:
    """Record the turn in the session (Redis) and in long-term memory (pgvector)."""
    add_turn(state, message, reply)
    await save_session(session_id, state)
    chat_memory.remember_in_background(session_id, "user", message)
    chat_memory.remember_in_background(session_id, "assistant", reply)


async def _ask_confirmation(
    session_id: str, state: dict[str, Any], message: str, kind: str
) -> dict[str, Any]:
    """Human in the loop: a sensitive question is not answered until the person confirms they
    want general information. The pending question is kept in the session."""
    logger.info("HITL: sensitive question held for confirmation (kind=%s)", kind)
    state["confirm"] = {"message": message, "kind": kind}
    body = _body(
        CONFIRM_TEXT,
        needs_input=True,
        suggestions=list(CONFIRM_CHIPS),
        hitl={"required": True, "kind": kind, "status": "awaiting_confirmation"},
    )
    await _finish_turn(session_id, state, message, body["text"])
    return {
        "session_id": session_id,
        "intent": "guardrail",
        "collected": _collected_view(state),
        "sources": [],
        **body,
    }


async def _finish_confirmation(
    session_id: str, state: dict[str, Any], message: str, pending: dict[str, Any]
) -> dict[str, Any]:
    if _YES_RE.match(message):
        logger.info("HITL: sensitive question confirmed (kind=%s)", pending["kind"])
        stance = await chat_guardrails.reply(pending["message"], pending["kind"])
        body = _body(
            stance["text"],
            suggestions=stance["suggestions"],
            guardrail=stance["kind"],
            answered_by=stance["answered_by"],
            hitl={"required": True, "kind": pending["kind"], "status": "confirmed"},
        )
    else:
        logger.info("HITL: sensitive question declined (kind=%s)", pending["kind"])
        body = _body(
            STOP_TEXT,
            suggestions=["What is risk vs return?", "What is diversification?"],
            hitl={"required": True, "kind": pending["kind"], "status": "declined"},
        )
    await _finish_turn(session_id, state, message, body["text"])
    return {
        "session_id": session_id,
        "intent": "guardrail",
        "collected": _collected_view(state),
        "sources": [],
        **body,
    }


async def chat_turn(session_id: str, message: str, research: bool = False) -> dict[str, Any]:
    message = message.strip()
    research_mode.set(research)
    if _RESET_RE.search(message):
        state = await reset_session(session_id)
        body = _body(
            "Starting fresh. What would you like to do?",
            needs_input=True,
            suggestions=list(STARTER_SUGGESTIONS),
        )
        return {"session_id": session_id, "intent": None, "collected": _collected_view(state), "sources": [], **body}

    state = await load_session(session_id)
    conversation_context.set(await chat_memory.build_context(session_id, state, message))
    master = await load_symbol_master()
    pending_more = state.pop("clarify", None)
    if pending_more and pending_more.get("kind") == "more_stocks" and state.get("last_result"):
        answered = await _answer_more_question(session_id, state, message, pending_more, master)
        if answered is not None:
            return answered
    if pending_more and pending_more.get("kind") == "penny":
        answered = await _answer_penny_question(session_id, state, message, pending_more, master)
        if answered is not None:
            return answered
    pending_confirm = state.pop("confirm", None)
    if pending_confirm and (_YES_RE.match(message) or _NO_RE.match(message)):
        return await _finish_confirmation(session_id, state, message, pending_confirm)
    sensitive_kind = None if asks_for_definition(message.lower()) else chat_guardrails.sensitive(message)
    if sensitive_kind:
        return await _ask_confirmation(session_id, state, message, sensitive_kind)
    pending_retry = state.get("retry")
    state["retry"] = None
    if pending_retry and _RETRY_RE.match(message):
        state["intent"] = pending_retry["intent"]
        state["slots"] = dict(pending_retry["slots"])
        retry_ex = Extraction(intent=pending_retry["intent"], slots=Slots())
        body = await _run_flow(state, retry_ex, master, message)
        await _finish_turn(session_id, state, message, body["text"])
        return {
            "session_id": session_id,
            "intent": pending_retry["intent"],
            "collected": _collected_view(state),
            "sources": [],
            **body,
        }
    # The answer to a question we asked is read together with the request it was about.
    pending_q = state.pop("clarify_q", None)
    effective = f"{pending_q['original']} ({message})" if pending_q else message
    ex = await extract(
        effective,
        last_asked=state["last_asked"],
        has_prior_plan=state.get("last_result") is not None or state["intent"] is not None,
        master=master,
    )
    question = None if pending_q else _model_question(state, ex, effective)
    if question is not None:
        state["clarify_q"] = {"original": message}
        intent, body = "unclear", question
    else:
        intent, body = await _dispatch(state, ex, effective, master)
    await _finish_turn(session_id, state, message, body["text"])
    return {
        "session_id": session_id,
        "intent": intent,
        "collected": _collected_view(state),
        "sources": [],
        **body,
    }


__all__ = ["OFF_TOPIC_MESSAGE", "chat_turn", "new_state"]
