"""Chat that keeps asking until horizon, amount, risk, and intent are known."""

from __future__ import annotations

import re
from typing import Any

from investment_agent.research.guidance import guide_symbol
from investment_agent.research.sip import build_sip

_sessions: dict[str, dict[str, Any]] = {}


def _state(session_id: str) -> dict[str, Any]:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "intent": None,
            "symbol": None,
            "horizon_years": None,
            "monthly_amount": None,
            "risk": None,
        }
    return _sessions[session_id]


def _absorb(state: dict[str, Any], message: str) -> None:
    text = message.lower()
    if any(word in text for word in ("sip", "monthly", "systematic")):
        state["intent"] = "sip"
    elif any(word in text for word in ("stock", "share", "buy", "invest in")):
        state["intent"] = state["intent"] or "stock"
    if "large" in text:
        state["risk"] = "large"
    elif "flexi" in text:
        state["risk"] = "flexi"
    elif "mid" in text:
        state["risk"] = "mid"
    elif "small" in text:
        state["risk"] = "small"
    years = re.search(r"(\d+)\s*(?:year|yr)", text)
    if years:
        state["horizon_years"] = int(years.group(1))
    amount = re.search(r"(?:₹|rs\.?|inr)?\s*(\d{3,7})", message, re.IGNORECASE)
    if amount and ("month" in text or "sip" in text or "budget" in text or "invest" in text):
        state["monthly_amount"] = float(amount.group(1))
    symbol = re.search(r"\b([A-Z]{2,12})\b", message)
    if symbol and symbol.group(1) not in {"SIP", "ETF", "NSE", "BSE", "AI"}:
        state["symbol"] = symbol.group(1)
        state["intent"] = "stock"


def _next_question(state: dict[str, Any]) -> str | None:
    if not state["intent"]:
        return "Do you want help with one stock, or with a monthly SIP?"
    if state["intent"] == "stock" and not state["symbol"]:
        return "Which symbol should I check, for example TCS or RELIANCE?"
    if not state["horizon_years"]:
        return "How many years will you stay invested?"
    if not state["monthly_amount"]:
        return "How much money per month, in rupees, can you put in?"
    if not state["risk"]:
        return "Which style fits you: large cap, flexi cap, mid cap, or small cap?"
    return None


async def chat_turn(session_id: str, message: str) -> dict[str, Any]:
    state = _state(session_id)
    _absorb(state, message.strip())
    question = _next_question(state)
    if question:
        return {
            "session_id": session_id,
            "needs_input": True,
            "text": question,
            "collected": {key: state[key] for key in ("intent", "symbol", "horizon_years", "monthly_amount", "risk")},
        }
    if state["intent"] == "sip":
        plan = await build_sip(float(state["monthly_amount"]), int(state["horizon_years"]), str(state["risk"]))
        lines = [
            f"{row['label']} ({row['symbol']}): ₹{row['monthly_inr']:,.0f} ({row['weight_pct']}%)"
            for row in plan["sleeves"]
        ]
        text = (
            f"For ₹{plan['monthly_amount']:,.0f} a month over {plan['horizon_years']} years, "
            f"a {plan['style']} mix is:\n" + "\n".join(lines) + f"\n{plan['note']}"
        )
        return {"session_id": session_id, "needs_input": False, "text": text, "plan": plan, "collected": state}
    guide = await guide_symbol(state["symbol"], int(state["horizon_years"]), float(state["monthly_amount"]))
    text = f"{guide['symbol']}: {guide['stance']}. {guide['summary']}"
    return {"session_id": session_id, "needs_input": False, "text": text, "guidance": guide, "collected": state}
