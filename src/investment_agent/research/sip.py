"""SIP mix from the monthly amount, horizon, and cap style.

Sleeve weights are deterministic (computed in Python), but the cap-style
choice is confirmed or overridden by the LLM, and each sleeve is priced
against the latest live NAV instead of a frozen weight table only.
"""

from __future__ import annotations

import logging
import re

from investment_agent.llm.factory import get_llm
from investment_agent.llm.providers import ModelTier
from investment_agent.market.indstocks import IndstocksError
from investment_agent.market.board import quote_for_symbol

logger = logging.getLogger(__name__)

MIXES = {
    "large": [("NIFTYBEES", "Large cap", 70), ("GOLDBEES", "Gold", 20), ("ITBEES", "Sector ETF", 10)],
    "flexi": [("NIFTYBEES", "Large cap", 45), ("JUNIORBEES", "Next 50", 25), ("GOLDBEES", "Gold", 15), ("BANKBEES", "Bank ETF", 15)],
    "mid": [("JUNIORBEES", "Next 50", 45), ("NIFTYBEES", "Large cap", 35), ("GOLDBEES", "Gold", 20)],
    "small": [("JUNIORBEES", "Next 50", 30), ("NIFTYBEES", "Large cap", 30), ("BANKBEES", "Bank ETF", 20), ("GOLDBEES", "Gold", 20)],
}

STYLE_REASONS = {
    "large": "A large-cap tilt prioritizes stability over this horizon.",
    "flexi": "A flexi-cap mix adapts across market caps, a reasonable core holding.",
    "mid": "The horizon is long enough for mid-cap swings to average out into extra growth.",
    "small": "A long horizon and conviction leave room for a small-cap growth tilt.",
}

_STYLE_PATTERN = re.compile(r"\b(large|flexi|mid|small)\b", re.IGNORECASE)


async def _live_price(symbol: str) -> float | None:
    try:
        quote = await quote_for_symbol(symbol, "NSE")
    except IndstocksError as exc:
        logger.warning("Live price unavailable for %s: %s", symbol, exc)
        return None
    return quote.get("live_price") if quote else None


async def _ai_style_pick(monthly_amount: float, horizon_years: int, requested_style: str) -> tuple[str, str]:
    """Ask the LLM to confirm or override the cap-style mix.

    Only a single classification word is extracted from the model's reply
    (via regex, tolerant of whatever shape `.content` comes back in across
    providers); the human-readable reason is generated deterministically in
    Python so a model's raw/structured output never leaks into the UI.
    Falls back to the requested style silently if the LLM call fails, so a
    model outage never blocks the calculator.
    """
    try:
        llm = get_llm(ModelTier.CHEAP)
        prompt = (
            "An Indian retail investor wants a monthly SIP of "
            f"₹{monthly_amount:,.0f} for {horizon_years} years. "
            f"They suggested the '{requested_style}' cap style. "
            "Prefer large or flexi for horizons under 5 years or smaller monthly amounts; "
            "only pick mid or small for longer horizons with room to ride out volatility. "
            "Reply with exactly one word: large, flexi, mid, or small."
        )
        response = await llm.ainvoke(prompt)
        raw = str(getattr(response, "content", response))
        match = _STYLE_PATTERN.search(raw)
        style = match.group(1).lower() if match else requested_style
        return style, STYLE_REASONS.get(style, "")
    except Exception as exc:
        logger.warning("SIP style AI suggestion failed, keeping requested style '%s': %s", requested_style, exc)
        return requested_style, ""


async def build_sip(monthly_amount: float, horizon_years: int, style: str) -> dict:
    key = style if style in MIXES else "flexi"
    if horizon_years < 5 and key == "small":
        key = "flexi"

    ai_style, ai_reason = await _ai_style_pick(monthly_amount, horizon_years, key)
    if ai_style in MIXES:
        key = ai_style

    rows = MIXES[key]
    sleeves = []
    for symbol, label, weight in rows:
        live_price = await _live_price(symbol)
        monthly_inr = round(monthly_amount * weight / 100, 2)
        sleeves.append(
            {
                "symbol": symbol,
                "label": label,
                "weight_pct": weight,
                "monthly_inr": monthly_inr,
                "live_price": live_price,
                "units": round(monthly_inr / live_price, 4) if live_price else None,
            }
        )

    note = (
        "Weights are a starting mix of listed ETFs, not a mutual-fund recommendation. "
        "A horizon under 5 years is kept in a flexi mix instead of a small-cap tilt."
    )
    if ai_reason:
        note = f"{ai_reason} {note}"

    return {
        "style": key,
        "requested_style": style,
        "horizon_years": horizon_years,
        "monthly_amount": monthly_amount,
        "sleeves": sleeves,
        "note": note,
    }
