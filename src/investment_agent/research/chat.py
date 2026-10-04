"""Chat that works for a total beginner and an experienced investor alike.

Every question is phrased so someone who has never invested before can answer it without
already knowing the jargon: no bare "cap style?" prompt, every question accepts "I don't
know"/"not sure" with a stated, sensible default, and a terse numeric reply (just "5",
just "5000") is read in context of whichever question was just asked rather than
requiring the exact phrasing ("5 years", "₹5000/month") a beginner may not think to use.

Routes a monthly-investment request to `suggest_mix` (real mutual funds, Workstream B) by
default — only an explicit "ETF" mention goes to the older `build_etf_sip`. An earlier
version of this module only knew about ETFs at all, which meant a user who typed "which
mutual funds should I invest in" got ETF jargon back; this fixes that mismatch.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.research.guidance import guide_symbol
from investment_agent.research.sip import CATEGORY_PLAIN_LABELS, build_etf_sip, rank_funds, suggest_mix

logger = logging.getLogger(__name__)

_sessions: dict[str, dict[str, Any]] = {}

DEFAULT_HORIZON_YEARS = 5
DEFAULT_RISK_PROFILE = "moderate"

_UNCERTAIN_PHRASES = (
    "don't know",
    "dont know",
    "not sure",
    "no idea",
    "unsure",
    "whatever",
    "you decide",
    "you choose",
    "no clue",
)

# Plain-language framing for both the risk question's answer and the fund categories
# `suggest_mix` returns — a beginner should never see a bare "flexi cap"/"aggressive"
# without a sentence explaining what that actually means for their money.
_RISK_PLAIN_LABELS = {
    "conservative": "playing it safe (steadier, smaller ups and downs)",
    "moderate": "a balanced mix (some ups and downs for better long-term growth)",
    "aggressive": "higher risk (bigger swings for potentially higher long-term growth)",
}
_RISK_TO_ETF_CAP_STYLE = {"conservative": "large", "moderate": "flexi", "aggressive": "small"}


def _state(session_id: str) -> dict[str, Any]:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "intent": None,  # "sip_fund" | "sip_etf" | "stock"
            "symbol": None,
            "horizon_years": None,
            "monthly_amount": None,
            "risk_profile": None,  # "conservative" | "moderate" | "aggressive"
            "last_asked": None,
        }
    return _sessions[session_id]


def _is_uncertain(text: str) -> bool:
    return any(phrase in text for phrase in _UNCERTAIN_PHRASES)


def _absorb(state: dict[str, Any], message: str, last_asked: str | None) -> None:
    text = message.lower().strip()
    uncertain = _is_uncertain(text)

    if state["intent"] is None:
        if "etf" in text:
            state["intent"] = "sip_etf"
        elif any(w in text for w in ("mutual fund", "sip", "monthly", "systematic")):
            state["intent"] = "sip_fund"
        elif any(w in text for w in ("stock", "share", "buy one", "one company")):
            state["intent"] = "stock"

    symbol_match = re.search(r"\b([A-Z]{2,12})\b", message)
    if symbol_match and symbol_match.group(1) not in {"SIP", "ETF", "NSE", "BSE", "AI"} and state["intent"] is None:
        state["symbol"] = symbol_match.group(1)
        state["intent"] = "stock"
    elif symbol_match and state["intent"] == "stock" and not state["symbol"]:
        if symbol_match.group(1) not in {"SIP", "ETF", "NSE", "BSE", "AI"}:
            state["symbol"] = symbol_match.group(1)

    years_match = re.search(r"(\d+)\s*(?:year|yr)", text)
    if years_match:
        state["horizon_years"] = int(years_match.group(1))
    elif last_asked == "horizon_years":
        bare_number = re.search(r"^\D*(\d{1,2})\D*$", text)
        if bare_number:
            state["horizon_years"] = int(bare_number.group(1))
        elif uncertain:
            state["horizon_years"] = DEFAULT_HORIZON_YEARS

    amount_match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d{3,7})", message, re.IGNORECASE)
    if amount_match and any(w in text for w in ("month", "sip", "budget", "invest", "rs", "₹", "rupee")) or last_asked == "monthly_amount" and amount_match:
        state["monthly_amount"] = float(amount_match.group(1))

    if any(w in text for w in ("safe", "steady", "low risk", "conservative", "play it safe")) or text in ("a", "1"):
        state["risk_profile"] = "conservative"
    elif any(w in text for w in ("balanced", "moderate", "medium risk", "flexi", "large cap")) or text in ("b", "2"):
        state["risk_profile"] = "moderate"
    elif any(w in text for w in ("aggressive", "high risk", "big swings", "small cap", "mid cap", "growth")) or text in (
        "c",
        "3",
    ):
        state["risk_profile"] = "aggressive"
    elif last_asked == "risk_profile" and uncertain:
        state["risk_profile"] = DEFAULT_RISK_PROFILE


def _next_question(state: dict[str, Any]) -> tuple[str, str] | None:
    if not state["intent"]:
        return (
            "intent",
            (
                "Would you like help picking one stock to buy, or setting up a regular monthly "
                "investment (called a SIP) spread across mutual funds? If you're not sure, most "
                "beginners start with a monthly SIP."
            ),
        )
    if state["intent"] == "stock" and not state["symbol"]:
        return ("symbol", "Which company are you interested in? You can use its name or stock symbol, for example TCS or RELIANCE.")
    if state["horizon_years"] is None:
        return (
            "horizon_years",
            (
                "How many years do you plan to stay invested before you might need this money? "
                "Just the number is fine (not sure? 5 years is a common starting point)."
            ),
        )
    if state["monthly_amount"] is None:
        return ("monthly_amount", "How much can you invest, in rupees? Just the number is fine, for example 5000.")
    if state["intent"] != "stock" and state["risk_profile"] is None:
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


def _collected_view(state: dict[str, Any]) -> dict[str, Any]:
    intent = state["intent"]
    frontend_intent = "stock" if intent == "stock" else "sip" if intent in ("sip_fund", "sip_etf") else None
    return {
        "intent": frontend_intent,
        "symbol": state["symbol"],
        "horizon_years": state["horizon_years"],
        "monthly_amount": state["monthly_amount"],
        "risk": state["risk_profile"],
    }


_FINANCE_WORDS = (
    "stock", "share", "mutual fund", "fund", "sip", "etf", "invest", "nifty", "sensex", "market",
    "portfolio", "gold", "debt", "bond", "equity", "nav", "dividend", "returns", "cap", "nse", "bse",
    "ipo", "rupee", "₹", "rs ", "risk", "amc", "elss", "demat", "broker", "price", "buy", "sell", "scheme",
)
_RANKING_WORDS = ("name some", "name the", "list", "rank", "top ", "best funds", "decreasing order", "specific fund")
_NEW_PLAN_WORDS = ("invest", "sip", "monthly", "per month", "a month")

OFF_TOPIC_MESSAGE = (
    "I can only help with the Indian stock market, mutual funds, SIPs and ETFs. "
    "That question doesn't look related — try something like “Should I buy TCS for 5 years?” "
    "or “Which mutual funds should I invest ₹10,000 a month in?”"
)


def _rule_intent(text: str, last_asked: str | None) -> str:
    t = text.lower()
    if last_asked and len(t.split()) <= 6:
        return "answer"  # a short reply to the question we just asked
    if not any(w in t for w in _FINANCE_WORDS) and not re.search(r"\b[A-Z]{2,12}\b", text):
        return "off_topic"
    if any(w in t for w in _RANKING_WORDS) and any(w in t for w in ("fund", "stock", "etf", "mutual")):
        return "fund_list" if "stock" not in t else "stock"
    if any(w in t for w in ("stock", "share")):
        return "stock"
    return "plan"


async def classify_intent(message: str, last_asked: str | None, has_plan: bool) -> str:
    """One of: off_topic | answer | fund_list | stock | plan. Cheap LLM first (so wording is
    understood, not keyword-matched), deterministic rules if the model is unavailable."""
    try:
        model = get_llm("cheap")
        prompt = (
            "Classify the user's message to an Indian investing assistant. Reply with ONE word:\n"
            "off_topic - not about stocks, mutual funds, SIPs, ETFs, gold, markets or personal investing\n"
            "answer - a short reply to the assistant's pending question"
            f" (pending question: {last_asked or 'none'})\n"
            "fund_list - asks to NAME specific mutual funds / a ranked list of funds\n"
            "stock - asks about a specific stock or its price/outlook\n"
            "plan - wants an allocation/plan for a monthly or lump-sum amount\n"
            f"A plan was already shown this session: {has_plan}.\n"
            f"Message: {message!r}"
        )
        reply = await model.ainvoke(prompt)
        word = extract_text(reply.content).strip().lower().split()[0].strip(".,:;\"'")
        if word in {"off_topic", "answer", "fund_list", "stock", "plan"}:
            return word
    except Exception as exc:
        logger.info("Intent classifier unavailable, using rules: %s", exc)
    return _rule_intent(message, last_asked)


async def _ranked_funds_reply(session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    risk = state["risk_profile"] or DEFAULT_RISK_PROFILE
    years = int(state["horizon_years"] or DEFAULT_HORIZON_YEARS)
    rows = await rank_funds(risk, years)
    if not rows:
        text = "I couldn't find scored mutual funds right now — the fund master may not be synced yet."
    else:
        lines, current = [], None
        for row in rows:
            if row["category"] != current:
                current = row["category"]
                lines.append(f"\n{row['category_label'].capitalize()}:")
            lines.append(f"{row['rank']}. {row['scheme_name']} — {row['trailing_return_pct']:.1f}% a year ({row['return_window']})")
        text = (
            f"Here are {len(rows)} funds for {_RISK_PLAIN_LABELS.get(risk, risk)} over {years} years, "
            "grouped by type and ranked by past yearly return (1 = strongest). Past returns don't "
            "guarantee future results — this isn't a recommendation." + "\n".join(lines)
        )
    return {
        "session_id": session_id,
        "needs_input": False,
        "text": text,
        "ranking": rows,
        "collected": _collected_view(state),
    }


async def chat_turn(session_id: str, message: str) -> dict[str, Any]:
    state = _state(session_id)
    last_asked = state.get("last_asked")
    plan_done = _next_question(state) is None
    intent = await classify_intent(message, last_asked, plan_done)

    if intent == "off_topic":
        return {
            "session_id": session_id,
            "needs_input": False,
            "error": True,
            "text": OFF_TOPIC_MESSAGE,
            "collected": _collected_view(state),
        }
    if intent == "fund_list":
        return await _ranked_funds_reply(session_id, state)
    if intent in ("stock", "plan") and plan_done:
        # A finished conversation must not silently replay the old answer: start fresh.
        _sessions.pop(session_id, None)
        state = _state(session_id)
        last_asked = None

    _absorb(state, message.strip(), last_asked)

    next_q = _next_question(state)
    if next_q:
        field, question = next_q
        state["last_asked"] = field
        return {"session_id": session_id, "needs_input": True, "text": question, "collected": _collected_view(state)}

    if state["intent"] == "stock":
        guide = await guide_symbol(state["symbol"], int(state["horizon_years"]), float(state["monthly_amount"]))
        text = f"{guide['symbol']}: {guide['stance']}. {guide['summary']}"
        return {"session_id": session_id, "needs_input": False, "text": text, "guidance": guide, "collected": _collected_view(state)}

    if state["intent"] == "sip_etf":
        cap_style = _RISK_TO_ETF_CAP_STYLE.get(state["risk_profile"], "flexi")
        plan = await build_etf_sip(float(state["monthly_amount"]), int(state["horizon_years"]), cap_style)
        lines = [
            f"{row['label']} ({row['symbol']}): ₹{row['monthly_inr']:,.0f} ({row['weight_pct']}%)" for row in plan["sleeves"]
        ]
        text = (
            f"For ₹{plan['monthly_amount']:,.0f} a month over {plan['horizon_years']} years, here's a starting ETF mix "
            "(bought through your broker — a different mechanism from a mutual fund SIP):\n"
            + "\n".join(lines)
            + f"\n{plan['note']}"
        )
        return {"session_id": session_id, "needs_input": False, "text": text, "plan": plan, "collected": _collected_view(state)}

    # Default SIP path: real mutual funds (Workstream B's suggest_mix), not ETFs.
    result = await suggest_mix(state["monthly_amount"], state["horizon_years"], state["risk_profile"])
    sleeves = [
        {
            "symbol": sleeve.get("scheme_code") or "—",
            "label": sleeve.get("category_label") or CATEGORY_PLAIN_LABELS.get(sleeve["category"], sleeve["category"])
            + (f" — {sleeve['scheme_name']}" if sleeve.get("scheme_name") else " (no specific fund matched yet)"),
            "weight_pct": sleeve["weight_pct"],
            "monthly_inr": sleeve["monthly_inr"],
        }
        for sleeve in result["sleeves"]
    ]
    plan = {
        "style": _RISK_PLAIN_LABELS.get(result["risk_profile"], result["risk_profile"]),
        "requested_style": result["risk_profile"],
        "horizon_years": result["horizon_years"],
        "monthly_amount": result["monthly_amount"],
        "note": result["note"],
        "sleeves": sleeves,
    }
    risk_label = _RISK_PLAIN_LABELS.get(result["risk_profile"], result["risk_profile"])
    text = (
        f"For ₹{result['monthly_amount']:,.0f}/month over {result['horizon_years']} years, going with {risk_label}, "
        "here's a mutual fund mix:\n"
        + "\n".join(f"{row['label']}: ₹{row['monthly_inr']:,.0f} ({row['weight_pct']}%)" for row in sleeves)
        + f"\n\n{result['explanation']}"
    )
    return {"session_id": session_id, "needs_input": False, "text": text, "plan": plan, "collected": _collected_view(state)}
