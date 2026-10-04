"""Horizon-aware guidance from live quotes. The model may only discuss numbers we pass in."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.market.tradingview import merge_fundamentals, tradingview_fundamentals
from investment_agent.market.yahoo_market import chart_symbol, company_fundamentals, quote_symbol
from investment_agent.research.stock_score import build_stock_score

logger = logging.getLogger(__name__)


def _range_return(candles: list[dict[str, Any]]) -> float | None:
    closes = [float(item["close"]) for item in candles if item.get("close") is not None]
    if len(closes) < 2 or closes[0] == 0:
        return None
    return round((closes[-1] / closes[0] - 1) * 100, 2)


def rule_stance(
    *,
    horizon_years: float,
    pe_ratio: float | None,
    day_change_pct: float | None,
    range_return_pct: float | None,
    span_label: str,
    roe_pct: float | None = None,
    debt_to_equity: float | None = None,
    sector: str | None = None,
) -> dict[str, Any]:
    """Deterministic fit for the holding span. Does not invent missing ratios."""
    reasons: list[str] = []
    blockers: list[str] = []
    if horizon_years < 3:
        blockers.append(
            f"A {span_label} span is shorter than the 3–5 year book this agent is built for."
        )
    if day_change_pct is not None and abs(day_change_pct) >= 12:
        blockers.append(
            f"The session move is {day_change_pct:.1f}%. Chasing a one-day spike does not fit a multi-year SIP."
        )
    if pe_ratio is None:
        blockers.append("Trailing P/E is not on the live quote, so valuation is incomplete.")
    elif pe_ratio > 45 and horizon_years <= 5:
        blockers.append(f"Trailing P/E is {pe_ratio:.1f}x, which is a rich multiple for a {span_label} hold.")
    elif pe_ratio > 0:
        reasons.append(f"Trailing P/E is {pe_ratio:.1f}x on the live quote.")
    if roe_pct is not None:
        if roe_pct < 12:
            blockers.append(f"Return on equity is {roe_pct:.1f}%, below the 12% quality line.")
        else:
            reasons.append(f"Return on equity is {roe_pct:.1f}%.")
    is_financial = bool(sector) and any(word in sector.lower() for word in ("financial", "bank"))
    if debt_to_equity is not None and not is_financial and debt_to_equity > 2:
        blockers.append(f"Debt to equity is {debt_to_equity:.2f}, above 2 for a non-financial company.")
    elif debt_to_equity is not None:
        reasons.append(f"Debt to equity is {debt_to_equity:.2f}.")
    if range_return_pct is not None:
        reasons.append(f"Price change over the chart window is {range_return_pct:.1f}%.")
    if blockers:
        stance = "AVOID" if horizon_years < 3 or (day_change_pct or 0) >= 12 else "WAIT"
    else:
        stance = "CONSIDER"
        reasons.append(f"The {span_label} span matches a long holding period.")
    return {"stance": stance, "reasons": reasons, "blockers": blockers}


async def guide_symbol(
    symbol: str,
    horizon_years: int,
    monthly_budget: float,
    exchange: str = "NSE",
    horizon_months: int = 0,
) -> dict[str, Any]:
    span = _span_label(horizon_years, horizon_months)
    total_years = horizon_years + horizon_months / 12
    quote = await quote_symbol(symbol, exchange)
    if quote is None:
        return {
            "symbol": symbol.upper(),
            "stance": "WAIT",
            "summary": "No live quote is available, so this name is not scored.",
            "reasons": [],
            "blockers": ["Live price is missing."],
            "good_points": [],
            "bad_points": ["We could not fetch a live price for this stock right now, so it cannot be scored."],
            "verdict_explanation": (
                "We could not pull a live price for this stock just now, so there is nothing to judge yet. "
                "Try again in a moment, or double check the symbol and exchange."
            ),
            "risk_level": "HIGH",
            "horizon_years": horizon_years,
            "shares_to_buy": None,
            "leftover_cash": None,
            "source": "market",
        }
    chart = await chart_symbol(symbol, "1y", exchange)
    candles = (chart or {}).get("candles") or []
    window_return = _range_return(candles)
    try:
        fundamentals = await company_fundamentals(symbol, exchange)
    except Exception:
        logger.info("Yahoo company profile unavailable for %s", symbol)
        fundamentals = {}
    try:
        import asyncio

        tradingview = await asyncio.to_thread(tradingview_fundamentals, symbol, exchange)
        fundamentals = merge_fundamentals(fundamentals, tradingview)
    except Exception:
        logger.info("TradingView screener unavailable for %s", symbol)
    pe = float(quote["pe_ratio"]) if quote.get("pe_ratio") is not None else fundamentals.get("pe_ratio")
    rules = rule_stance(
        horizon_years=total_years,
        pe_ratio=pe,
        day_change_pct=float(quote.get("day_change_percentage") or 0),
        range_return_pct=window_return,
        span_label=span,
        roe_pct=fundamentals.get("roe_pct"),
        debt_to_equity=fundamentals.get("debt_to_equity"),
        sector=fundamentals.get("sector"),
    )
    live_price = float(quote["live_price"])
    shares_to_buy = int(monthly_budget // live_price) if live_price > 0 else None
    leftover_cash = round(monthly_budget - (shares_to_buy or 0) * live_price, 2) if shares_to_buy is not None else None

    facts = {
        "symbol": quote["symbol"],
        "name": quote["name"],
        "live_price_inr": quote["live_price"],
        "day_change_pct": quote["day_change_percentage"],
        "pe_ratio": pe,
        "market_cap_cr": quote.get("market_cap_cr"),
        "fundamentals": fundamentals,
        "one_year_price_change_pct": window_return,
        "horizon_years": horizon_years,
        "monthly_budget_inr": monthly_budget,
        "shares_affordable_this_month": shares_to_buy,
        "rule_stance": rules["stance"],
    }
    narrative = await _narrate(facts, rules)
    risk_level = narrative.get("risk_level") or _fallback_risk_level(narrative.get("stance") or rules["stance"])
    fallback_good, fallback_bad = _plain_language_points(fundamentals, pe, window_return, total_years)

    stance = narrative.get("stance") or rules["stance"]
    multi_factor_score = await _multi_factor_overall_score(quote["symbol"], exchange)
    # Gap 4: rule_stance stays the hard floor (a blocker can never be overridden); the
    # richer F2 score may only *tighten* a CONSIDER down to WAIT when it disagrees, never
    # loosen WAIT/AVOID — same invariant _narrate already enforces for the LLM's opinion.
    if stance == "CONSIDER" and multi_factor_score is not None and multi_factor_score < 50.0:
        stance = "WAIT"

    return {
        "symbol": quote["symbol"],
        "name": quote["name"],
        "stance": stance,
        "multi_factor_score": multi_factor_score,
        "summary": narrative.get("summary") or _fallback_summary(quote["symbol"], rules),
        "reasons": narrative.get("reasons") or rules["reasons"],
        "blockers": narrative.get("blockers") or rules["blockers"],
        "good_points": narrative.get("good_points") or fallback_good,
        "bad_points": narrative.get("bad_points") or fallback_bad,
        "verdict_explanation": narrative.get("verdict_explanation")
        or _fallback_verdict_explanation(quote["symbol"], rules, monthly_budget, shares_to_buy, live_price),
        "risk_level": risk_level,
        "horizon_years": horizon_years,
        "monthly_budget": monthly_budget,
        "shares_to_buy": shares_to_buy,
        "leftover_cash": leftover_cash,
        "live_price": quote["live_price"],
        "pe_ratio": pe,
        "one_year_price_change_pct": window_return,
        "fundamentals": fundamentals,
        "source": narrative.get("source") or "rules",
    }


def _span_label(years: int, months: int) -> str:
    parts: list[str] = []
    if years:
        parts.append(f"{years} year" if years == 1 else f"{years} years")
    if months:
        parts.append(f"{months} month" if months == 1 else f"{months} months")
    return " ".join(parts) or "0 months"


def _fallback_summary(symbol: str, rules: dict[str, Any]) -> str:
    stance = rules["stance"]
    if stance == "CONSIDER":
        return f"{symbol} fits the selected holding span on the live numbers that are present."
    if stance == "AVOID":
        return f"{symbol} does not fit the selected holding span."
    return f"{symbol} needs more evidence before a buy decision for this holding span."


def _plain_language_points(
    fundamentals: dict[str, Any],
    pe_ratio: float | None,
    window_return_pct: float | None,
    horizon_years: float,
) -> tuple[list[str], list[str]]:
    """Translate the raw ratios into everyday language for someone who has never bought a stock.

    Used only when the LLM call in `_narrate` doesn't return its own good/bad points, so a
    beginner never sees a bare ratio like "P/E is 15.1x" with no explanation of what it means.
    """
    good: list[str] = []
    bad: list[str] = []

    roe = fundamentals.get("roe_pct")
    if isinstance(roe, (int, float)):
        if roe >= 15:
            good.append("The company is good at turning the money invested in it into profit — a sign of efficient management.")
        elif roe < 8:
            bad.append("The company isn't very efficient at turning its money into profit right now.")

    if isinstance(pe_ratio, (int, float)) and pe_ratio > 0:
        if pe_ratio <= 25:
            good.append("The share price looks reasonably priced compared to how much profit the company makes each year.")
        elif pe_ratio > 45:
            bad.append("The share price is expensive compared to current profits — you're paying a lot for future growth that may not show up.")

    debt = fundamentals.get("debt_to_equity")
    if isinstance(debt, (int, float)):
        if debt <= 1:
            good.append("The company doesn't owe much money compared to what it owns, which makes it less risky if business slows down.")
        elif debt > 2:
            bad.append("The company has a lot of borrowed money, which can be risky if it struggles to repay it.")

    revenue_growth = fundamentals.get("revenue_growth_pct")
    if isinstance(revenue_growth, (int, float)):
        if revenue_growth >= 10:
            good.append("The company's sales have been growing at a healthy pace.")
        elif revenue_growth < 0:
            bad.append("The company's sales have actually been shrinking recently.")

    if isinstance(window_return_pct, (int, float)):
        if window_return_pct <= -20:
            bad.append("The share price has dropped a lot over the past year, so it's been a bumpy ride for anyone holding it.")
        elif window_return_pct >= 20:
            good.append("The share price has climbed a good amount over the past year.")

    if horizon_years < 3:
        bad.append("You're planning to hold for a fairly short time, and stock prices can swing a lot in the short term — that adds risk.")

    if not good:
        good.append("There isn't enough solid data here to point to a clear strength yet.")
    if not bad:
        bad.append("Nothing in the numbers we checked stands out as an immediate red flag, but always expect some ups and downs.")

    return good, bad


async def _multi_factor_overall_score(symbol: str, exchange: str) -> float | None:
    """Gap 4: the F2 deterministic score (research/stock_score.py), best-effort.

    Bounded with a timeout and wrapped so a slow/failing score never blocks or breaks
    `/research/guidance` — it can only ever add a stricter check on top of `rule_stance`,
    never become a hard dependency of this already-shipped endpoint. Most of the data this
    needs (quote, fundamentals, statements) was just fetched above and is now cache-warm
    (Gap 6), so this second fetch is cheap in practice, not a duplicate full round trip.
    """
    try:
        card = await asyncio.wait_for(build_stock_score(symbol, exchange), timeout=12.0)
    except Exception as exc:
        logger.info("Multi-factor score unavailable for %s: %s", symbol, exc)
        return None
    if card.get("status") != "OK":
        return None
    overall = card.get("overall")
    return float(overall) if isinstance(overall, (int, float)) else None


def _fallback_risk_level(stance: str) -> str:
    return {"CONSIDER": "MEDIUM", "WAIT": "MEDIUM", "AVOID": "HIGH"}.get(stance, "MEDIUM")


def _fallback_verdict_explanation(
    symbol: str,
    rules: dict[str, Any],
    monthly_budget: float,
    shares_to_buy: int | None,
    live_price: float,
) -> str:
    """A plain-English fallback used only if the model call fails, written for someone who has never bought a stock."""
    stance = rules["stance"]
    money_line = (
        f"At today's price of ₹{live_price:,.2f}, your ₹{monthly_budget:,.0f} a month buys about "
        f"{shares_to_buy} share{'s' if shares_to_buy != 1 else ''} of {symbol}."
        if shares_to_buy
        else f"At today's price of ₹{live_price:,.2f}, ₹{monthly_budget:,.0f} a month is not enough to buy even one share of {symbol}."
    )
    if stance == "CONSIDER":
        verdict = f"{symbol} looks reasonable for the span you picked, based on the numbers we could check."
    elif stance == "AVOID":
        verdict = f"{symbol} does not look like a good fit right now for the span you picked."
    else:
        verdict = f"{symbol} is a maybe — there isn't enough solid data yet to be confident either way."
    return f"{verdict} {money_line}"


async def _narrate(facts: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are a patient Indian equity guide explaining a stock to someone who has NEVER bought a "
        "stock before and does not know basic investing terms. Use only the JSON facts below — do not "
        "invent ROE, debt, promoter pledge, filings, or prices that are absent. "
        "Return JSON with keys: "
        "stance (CONSIDER, WAIT, or AVOID), "
        "summary (one plain sentence), "
        "reasons (array of short technical bullet points, for an experienced reader), "
        "blockers (array of short technical bullet points, for an experienced reader), "
        "good_points (array of 2-4 short bullet points in simple everyday language, explaining what looks "
        "good about this stock — no jargon, as if explaining to a friend who has never invested), "
        "bad_points (array of 2-4 short bullet points in simple everyday language, explaining the risks or "
        "what looks bad — no jargon), "
        "verdict_explanation (a 3-5 sentence plain-English paragraph for a total beginner: say clearly "
        "whether this looks like a reasonable buy or not and why in simple terms, mention how many shares "
        "'shares_affordable_this_month' lets them buy with their monthly budget and what that costs, and "
        "give one plain-language risk-level takeaway), "
        "risk_level (LOW, MEDIUM, or HIGH — how risky this looks for a beginner over the given horizon). "
        "stance must stay CONSIDER only if rule_stance is CONSIDER. "
        f"Facts: {json.dumps(facts)}"
    )
    try:
        model = get_llm("primary")
        reply = await model.ainvoke(prompt)
        text = extract_text(reply.content)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no json")
        parsed = json.loads(text[start : end + 1])
        stance = str(parsed.get("stance") or rules["stance"]).upper()
        if stance not in {"CONSIDER", "WAIT", "AVOID"}:
            stance = rules["stance"]
        if rules["stance"] != "CONSIDER":
            stance = rules["stance"]
        risk_level = str(parsed.get("risk_level") or "").upper()
        if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
            risk_level = ""
        return {
            "stance": stance,
            "summary": str(parsed.get("summary") or ""),
            "reasons": [str(item) for item in parsed.get("reasons") or rules["reasons"]],
            "blockers": [str(item) for item in parsed.get("blockers") or rules["blockers"]],
            "good_points": [str(item) for item in parsed.get("good_points") or []],
            "bad_points": [str(item) for item in parsed.get("bad_points") or []],
            "verdict_explanation": str(parsed.get("verdict_explanation") or ""),
            "risk_level": risk_level,
            "source": "llm",
        }
    except Exception as exc:
        logger.info("Guidance model unavailable, using rules: %s", exc)
        return {"source": "rules"}
