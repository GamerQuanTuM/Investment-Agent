"""Chat handler for "give me N stocks for ₹X".

The picker (`portfolio/stock_picker.py`) decides every symbol, share count and amount. This
module only fetches its inputs, wraps the result for the UI and writes the words around it:
a cheap-tier model may write a 2-3 sentence plain-English intro from the structured result,
and `llm_guard.is_grounded` throws that text away (falling back to the template) if it
contains any ticker or number the result does not hold. The per-stock lines, totals, reality
check and disclaimer are always deterministic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.market import live_universe
from investment_agent.portfolio.stock_picker import (
    DEFAULT_STOCKS,
    Candidate,
    build_stock_plan,
    clamp_count,
    filter_candidates,
    load_pick_universe,
    pick_filters,
)
from investment_agent.research.evidence import Evidence, SourceType
from investment_agent.research.formatting import inr, normalize_money_text
from investment_agent.research.llm_guard import is_grounded

logger = logging.getLogger(__name__)

LOADING_TEXT = (
    "I'm loading fresh market data, this takes about a minute. "
    "Tap “Try again” in a moment and I'll build your list."
)
PROVIDERS_DOWN_TEXT = (
    "I couldn't reach the market data providers right now, please try again in a few minutes."
)
RETRY_CHIP = "Try again"
NARRATION_TIMEOUT_SECONDS = 12.0
CAUTIOUS_NOTE = (
    "This is already my most cautious setting: mostly large, established companies, with at most "
    "a fifth in mid-sized ones and no small caps. It can still fall, and no list removes risk."
)
BEGINNER_RISK_LINE = (
    "Stocks can fall as well as rise, so only invest money you won't need soon."
)
FOLLOWUP_CHIPS = ["Prefer one index fund/ETF SIP instead?", "What about safer ones?"]


def _unavailable(text: str, reason: str, *, status: str = "DATA_UNAVAILABLE", retry: bool = False) -> dict[str, Any]:
    chips = ["What is an ETF?", "Plan a ₹5,000 monthly SIP"]
    return {
        "text": text,
        "needs_input": False,
        "suggestions": [RETRY_CHIP, *chips] if retry else chips,
        "data_status": status,
        "data_reason": reason,
        "stock_plan": None,
        "sources": [],
        "retry": retry,
    }


async def _eligible_candidates() -> tuple[list[Candidate], dict[str, int], str | None]:
    """Stocks that pass the data checks: from the database when it is populated, otherwise
    from the live fallback. The last item is None, "loading" or "unreachable"."""
    filters = pick_filters()
    universe = await load_pick_universe()
    kept, excluded = filter_candidates(universe, now=datetime.now(UTC), **filters)
    if kept:
        return kept, excluded, None
    outcome = await live_universe.get_candidates()
    if outcome.status == "loading":
        return [], {}, "loading"
    if outcome.status == "failed":
        return [], {}, "unreachable"
    kept, excluded = filter_candidates(outcome.candidates, now=datetime.now(UTC), **filters)
    return kept, excluded, None if kept else "unreachable"


def template_summary(plan: dict[str, Any], *, monthly: bool) -> str:
    n = len(plan["rows"])
    per = " a month" if monthly else ""
    return (
        f"Here are {n} stocks for your {inr(plan['budget'])}{per}, picked by past quality, valuation, "
        "price trend and steadiness, with no more than two from any one sector. "
        "These describe the past, not a forecast."
    )


def _facts_for_model(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "budget_inr": plan["budget"],
        "total_invested_inr": plan["total_invested"],
        "leftover_inr": plan["leftover"],
        "data_as_of": plan["data_as_of"],
        "stocks": [
            {
                "symbol": r["symbol"],
                "sector": r["sector"],
                "shares": r["shares"],
                "amount_inr": r["amount_inr"],
                "weight_pct": r["weight_pct"],
            }
            for r in plan["rows"]
        ],
        "sector_split_pct": plan["sector_split"],
    }


async def narrate(plan: dict[str, Any], *, monthly: bool) -> str:
    """Model intro if it is fully grounded in `plan`, else the deterministic template."""
    fallback = template_summary(plan, monthly=monthly)
    facts = _facts_for_model(plan)
    try:
        model = get_llm("cheap")
        reply = await asyncio.wait_for(
            model.ainvoke(
                "Write 2 or 3 short plain-English sentences introducing this stock list for a "
                "beginner. Use ONLY the symbols and numbers in the JSON; do not add any other "
                "company, price, return or percentage. Write every rupee amount with the ₹ sign "
                "and digit grouping (for example ₹8,552), never as INR or a bare number. "
                "Do not predict, give targets, or tell the user to buy now. State that these are "
                "past figures, not a forecast.\n"
                f"JSON: {json.dumps(facts)}"
            ),
            timeout=NARRATION_TIMEOUT_SECONDS,
        )
        text = extract_text(reply.content).strip()
    except Exception as exc:
        logger.info("Stock-list narration unavailable: %s", exc)
        return fallback
    if is_grounded(text, {"plan": facts, "budget": plan["budget"]}, [r["symbol"] for r in plan["rows"]]):
        return normalize_money_text(text)
    logger.info("Stock-list narration rejected by the grounding check")
    return fallback


def render_rows(plan: dict[str, Any], *, beginner: bool) -> str:
    lines = []
    for i, r in enumerate(plan["rows"], start=1):
        line = (
            f"{i}. **{r['symbol']}** ({r['sector']}): {r['shares']} share{'s' if r['shares'] != 1 else ''} "
            f"at {inr(r['price'])} = {inr(r['amount_inr'])} ({r['weight_pct']}%)"
        )
        if not beginner and r["why"]:
            line += f" — {r['why'][0]}"
        lines.append(line)
    return "\n".join(lines)


def _sources(plan: dict[str, Any], chosen: dict[str, Candidate]) -> list[dict[str, Any]]:
    price_date = datetime.fromisoformat(plan["data_as_of"]).replace(tzinfo=UTC) if plan["data_as_of"] else None
    first = chosen.get(plan["rows"][0]["symbol"]) if plan["rows"] else None
    sources = [
        Evidence(
            claim=f"Latest closing prices for {len(plan['rows'])} stocks",
            source_name=first.price_source_name if first else "INDstocks daily bars",
            source_url=first.price_source_url if first else "https://api.indstocks.com/market/historical/1day",
            source_type=SourceType.INDSTOCKS,
            data_date=price_date,
        )
    ]
    seen: set[str] = set()
    for row in plan["rows"]:
        cand = chosen.get(row["symbol"])
        if cand is None or not cand.source_name or cand.source_name in seen or len(seen) >= 3:
            continue
        seen.add(cand.source_name)
        sources.append(
            Evidence(
                claim="Fundamentals (ROE, ROCE, growth, debt, market cap)",
                source_name=cand.source_name,
                source_url=cand.source_url,
                source_type=SourceType.FINANCIAL_DATA_PROVIDER,
                data_date=cand.data_date,
            )
        )
    return [s.model_dump(mode="json") for s in sources]


async def stock_list_reply(slots: dict[str, Any]) -> dict[str, Any]:
    """Build the chat reply for a stock-list request whose amount is already known."""
    kept, excluded, problem = await _eligible_candidates()
    if problem == "loading":
        return _unavailable(LOADING_TEXT, "loading", status="LOADING", retry=True)
    if problem or not kept:
        return _unavailable(PROVIDERS_DOWN_TEXT, "providers_unreachable", retry=True)

    beginner = slots.get("experience_level") == "beginner"
    monthly = slots.get("amount_kind") == "monthly"
    count = clamp_count(slots.get("stock_count") or DEFAULT_STOCKS)
    plan = build_stock_plan(
        kept,
        budget=float(slots["amount_inr"]),
        count=count,
        risk_profile=slots.get("risk_profile"),
        experience_level=slots.get("experience_level"),
        sectors_wanted=slots.get("sectors_wanted") or None,
        horizon_years=slots.get("horizon_years") or 5,
    )
    if plan["status"] != "OK":
        return _unavailable(plan["message"], plan["reason"])

    plan["excluded"] = excluded
    intro = await narrate(plan, monthly=monthly)
    blocks = [intro, render_rows(plan, beginner=beginner)]
    blocks.append(
        f"Invested {inr(plan['total_invested'])}; {inr(plan['leftover'])} left as cash "
        f"(shares are bought whole). Prices as of {plan['data_as_of']}."
    )
    if beginner:
        blocks.append(
            "A share is a small slice of a company; the % is how much of your money goes to each. "
            + BEGINNER_RISK_LINE
        )
        if plan["budget"] / max(1, len(plan["rows"])) < 5000:
            blocks.append(
                "Tip: with a small amount, one diversified index fund or ETF is usually simpler and cheaper."
            )
    if plan["risk_profile"] == "conservative" and slots.get("risk_profile") == "conservative":
        blocks.append(CAUTIOUS_NOTE)
    blocks.extend(c for c in plan["caveats"] if c)
    blocks.append(f"*{plan['disclaimer']}*")

    chosen = {c.symbol: c for c in kept}
    suggestions = list(FOLLOWUP_CHIPS)
    if len(plan["rows"]) != 8:
        suggestions.append("Make it 8 stocks")
    return {
        "text": "\n\n".join(blocks),
        "needs_input": False,
        "suggestions": suggestions,
        "stock_plan": plan,
        "sources": _sources(plan, chosen),
        "plan_defaults": {"horizon_years": plan["horizon_years"], "risk_profile": plan["risk_profile"]},
    }
