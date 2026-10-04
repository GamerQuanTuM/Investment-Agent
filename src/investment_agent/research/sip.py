"""SIP calculators: a listed-ETF mix (`build_etf_sip`, unchanged behaviour, relabelled
honestly) and the real-mutual-fund tools added in Workstream B (`build_fund_sip`,
`suggest_mix`).

Python (`portfolio/fund_metrics.py`) computes every number. The LLM (CHEAP tier) may only
narrate a result already computed, in plain language, and every call has a deterministic
fallback text so a model outage never blocks the calculator (same invariant as
`research/stock_score.py`).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from investment_agent.db.models.market import MutualFundScheme
from investment_agent.db.session import async_session_factory
from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.market.amfi import classify_option, classify_plan
from investment_agent.market.board import quote_for_symbol
from investment_agent.market.indstocks import IndstocksError
from investment_agent.market.mfapi import fetch_nav_history, list_schemes
from investment_agent.portfolio.fund_metrics import (
    ltcg_stcg_estimate,
    period_return_pct,
    project_sip,
    sip_backtest,
    trailing_cagr,
)

logger = logging.getLogger(__name__)

# --- ETF mix (pre-existing feature, relabelled) --------------------------------------

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


async def _live_price(symbol: str) -> float | None:
    try:
        quote = await quote_for_symbol(symbol, "NSE")
    except IndstocksError as exc:
        logger.warning("Live price unavailable for %s: %s", symbol, exc)
        return None
    return quote.get("live_price") if quote else None


async def build_etf_sip(monthly_amount: float, horizon_years: int, style: str) -> dict[str, Any]:
    """Starting mix of listed ETFs (NIFTYBEES/JUNIORBEES/GOLDBEES/BANKBEES/ITBEES), priced
    against live NAVs. Deterministic style selection only — the one-word LLM style
    classifier this function used to call (`_ai_style_pick`) was removed: it added a model
    round-trip to override a choice that was already deterministic and reasonable, with no
    real signal the LLM could add (it saw none of the user's actual financial situation)."""
    key = style if style in MIXES else "flexi"
    if horizon_years < 5 and key == "small":
        key = "flexi"

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
        f"{STYLE_REASONS[key]} Weights are a starting mix of listed ETFs bought via your "
        "broker (not a mutual-fund SIP, which runs through the AMC/RTA instead) — not a "
        "specific mutual-fund recommendation. A horizon under 5 years is kept in a flexi "
        "mix instead of a small-cap tilt."
    )

    return {
        "mode": "etf",
        "style": key,
        "requested_style": style,
        "horizon_years": horizon_years,
        "monthly_amount": monthly_amount,
        "sleeves": sleeves,
        "note": note,
    }


# --- Real mutual fund SIP (Workstream B, B4) ------------------------------------------


def _fallback_fund_explanation(
    scheme_name: str | None, backtest: dict[str, Any], projection: dict[str, Any]
) -> str:
    name = scheme_name or "This fund"
    xirr = backtest.get("xirr_pct")
    nominal = projection.get("nominal_corpus")
    parts = [f"{name}: "]
    if xirr is not None:
        parts.append(f"a historical backtest of this SIP would have returned about {xirr:.1f}% annualized. ")
    if nominal is not None:
        parts.append(f"At the assumed future rate, the projected corpus is roughly ₹{nominal:,.0f}.")
    text = "".join(parts).strip()
    return text or f"Not enough data was available to summarize {name} right now."


async def _explain_fund_sip(
    scheme_name: str | None, backtest: dict[str, Any], projection: dict[str, Any], tax: dict[str, Any]
) -> str:
    try:
        model = get_llm("cheap")
        prompt = (
            "Explain this mutual fund SIP result in 2-3 plain sentences for a retail "
            "investor with basic knowledge. Use ONLY the numbers given — do not invent or "
            "adjust any figure, and clearly note the projection is an assumption, not a "
            "forecast. "
            f"Scheme: {scheme_name}. Backtest: {json.dumps(backtest)}. "
            f"Projection: {json.dumps(projection)}. Tax estimate: {json.dumps(tax)}."
        )
        reply = await model.ainvoke(prompt)
        text = extract_text(reply.content)
        text = text.strip()
        return text or _fallback_fund_explanation(scheme_name, backtest, projection)
    except Exception as exc:
        logger.info("Fund SIP explanation model unavailable for %s: %s", scheme_name, exc)
        return _fallback_fund_explanation(scheme_name, backtest, projection)


async def build_fund_sip(
    scheme_code: str,
    monthly_amount: float,
    years: int,
    step_up_pct: float = 0.0,
    inflation_pct: float = 0.0,
) -> dict[str, Any]:
    """Backtest (real historical NAVs) + forward projection + tax estimate + plain-language
    explanation for a single real mutual fund SIP. `DATA_UNAVAILABLE` if the fund's NAV
    history can't be fetched."""
    scheme_code = scheme_code.strip()
    history = await fetch_nav_history(scheme_code)
    if history is None or not history.get("nav_history"):
        return {
            "scheme_code": scheme_code,
            "status": "DATA_UNAVAILABLE",
            "message": "NAV history could not be fetched for this scheme.",
        }

    nav_history = history["nav_history"]
    latest_date = date.fromisoformat(nav_history[0]["date"])
    earliest_date = date.fromisoformat(nav_history[-1]["date"])
    backtest_start = max(earliest_date, latest_date - timedelta(days=5 * 365))
    backtest = sip_backtest(nav_history, monthly_amount, backtest_start, step_up_pct)

    # Assumed forward rate: this fund's own trailing 5y (falling back to 3y, then a
    # conservative flat 10%) rather than a single global constant — a debt fund and a
    # small-cap fund should not be projected at the same assumed rate.
    assumed_return = trailing_cagr(nav_history, 5) or trailing_cagr(nav_history, 3) or 10.0
    projection = project_sip(monthly_amount, years, assumed_return, step_up_pct, inflation_pct)

    is_equity = "equity" in (history.get("scheme_category") or "").lower()
    tax: dict[str, Any] = {"tax": None, "tax_type": "DATA_UNAVAILABLE", "rate_pct": None}
    if backtest.get("current_value") is not None and backtest.get("invested") is not None:
        gains = round(backtest["current_value"] - backtest["invested"], 2)
        holding_years = (
            date.fromisoformat(backtest["end_date"]) - date.fromisoformat(backtest["start_date"])
        ).days / 365.0
        tax = ltcg_stcg_estimate(gains, holding_years, is_equity=is_equity)

    explanation = await _explain_fund_sip(history.get("scheme_name"), backtest, projection, tax)

    return {
        "mode": "fund",
        "scheme_code": history["scheme_code"],
        "scheme_name": history.get("scheme_name"),
        "status": "OK",
        "assumed_annual_return_pct": assumed_return,
        "backtest": backtest,
        "projection": {"assumption_note": "This is an assumption, not a forecast.", **projection},
        "tax_estimate": tax,
        "explanation": explanation,
    }


# Horizon/risk-profile -> target weights by SEBI fund group. Deliberately simple and
# auditable (a lookup table, not a model) — the spec asks for deterministic weighting;
# the LLM only narrates the result (see `_explain_suggestion`).
_RISK_WEIGHTS: dict[str, dict[str, float]] = {
    "conservative": {"debt": 60.0, "large cap": 30.0, "gold": 10.0},
    "moderate": {"large cap": 40.0, "flexi cap": 30.0, "debt": 20.0, "gold": 10.0},
    "aggressive": {"flexi cap": 30.0, "mid cap": 25.0, "small cap": 20.0, "large cap": 15.0, "gold": 10.0},
}

# `classify_sebi_group` (market/amfi.py) produces these group labels; map to the keys
# above since the weight table above is written for readability, not the stored casing.
_GROUP_LABELS = {
    "debt": "debt",
    "large": "large cap",
    "flexi": "flexi cap",
    "mid": "mid cap",
    "small": "small cap",
    "gold": "gold",
}

_CANDIDATE_POOL_PER_GROUP = 12
_FETCH_TIMEOUT_SECONDS = 8.0
_NAV_FETCHES = asyncio.Semaphore(8)

# Weight-table keys are readable phrases; the scheme master stores the short group.
_STORED_GROUP = {
    "debt": "debt",
    "large cap": "large",
    "flexi cap": "flexi",
    "mid cap": "mid",
    "small cap": "small",
    "gold": "gold",
}
_CATALOGUE_LABEL = {
    "debt": "Debt",
    "large cap": "Large cap",
    "flexi cap": "Flexi cap",
    "mid cap": "Mid cap",
    "small cap": "Small cap",
    "gold": "Gold",
}
RETURN_SPANS = {
    "quarter": (0.25, "this quarter"),
    "6m": (0.5, "the last 6 months"),
    "1y": (1.0, "the last year"),
    "3y": (3.0, "the last 3 years"),
    "5y": (5.0, "the last 5 years"),
}

# Plain-English translation of the SEBI-style category keys above. Beginners have no
# reason to know what "flexi cap" means; this is the single source of truth for that
# translation — both the API response (`category_label` on each sleeve, so any UI can
# show it) and the LLM narration prompt below use it, so a beginner never sees raw
# jargon in either place. `research/chat.py` reads this dict directly rather than
# keeping its own copy.
CATEGORY_PLAIN_LABELS = {
    "debt": "safer, bond-like investments",
    "large cap": "large, well-established companies",
    "flexi cap": "a flexible mix across company sizes",
    "mid cap": "medium-sized, growing companies",
    "small cap": "smaller, higher-growth companies",
    "gold": "gold (a hedge against market swings)",
}


def _resolve_risk_weights(horizon_years: int, risk_profile: str) -> dict[str, float]:
    key = risk_profile.strip().lower() if risk_profile.strip().lower() in _RISK_WEIGHTS else "moderate"
    if horizon_years < 3:
        # A short horizon overrides an aggressive request — there isn't enough time to
        # ride out mid/small-cap volatility, mirroring the ETF mix's horizon guard.
        key = "conservative"
    return _RISK_WEIGHTS[key]


class _NamedScheme:
    """Enough of a scheme row for scoring when the pick comes from the live catalogue."""

    def __init__(self, scheme_code: str, name: str) -> None:
        self.scheme_code = scheme_code
        self.name = name


def _spread(items: list[Any], limit: int) -> list[Any]:
    """Take `limit` items spread across the list so one fund house doesn't fill the pool."""
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(index * step)] for index in range(limit)]


async def _candidates_for_group(sebi_group: str, limit: int) -> list[Any]:
    stored = _STORED_GROUP.get(sebi_group, sebi_group)
    async with async_session_factory() as session:
        try:
            stmt = (
                select(MutualFundScheme)
                .where(
                    MutualFundScheme.sebi_group == stored,
                    MutualFundScheme.plan == "direct",
                    MutualFundScheme.option == "growth",
                )
                .order_by(MutualFundScheme.name)
                .limit(limit)
            )
            rows = list((await session.scalars(stmt)).all())
        except Exception as exc:
            logger.warning("Fund candidate lookup failed for group %s: %s", sebi_group, exc)
            rows = []
    if rows:
        return rows
    return await _live_candidates(sebi_group, limit)


async def _live_candidates(sebi_group: str, limit: int) -> list[_NamedScheme]:
    """Direct Growth schemes in this category from the live mfapi catalogue."""
    label = _CATALOGUE_LABEL.get(sebi_group)
    if label is None:
        return []
    try:
        schemes = await list_schemes()
    except Exception as exc:
        logger.warning("Live catalogue unavailable for %s: %s", sebi_group, exc)
        return []
    matched = [
        scheme
        for scheme in schemes
        if scheme.get("category") == label
        and classify_plan(scheme["scheme_name"]) == "direct"
        and classify_option(scheme["scheme_name"]) == "growth"
    ]
    return [_NamedScheme(scheme["scheme_code"], scheme["scheme_name"]) for scheme in _spread(matched, limit)]


async def _best_pick(scheme: Any, span_years: float = 5.0) -> dict[str, Any] | None:
    """Score one scheme by its return over `span_years`. None if that window isn't covered."""
    async with _NAV_FETCHES:
        try:
            history = await asyncio.wait_for(fetch_nav_history(scheme.scheme_code), timeout=_FETCH_TIMEOUT_SECONDS)
        except Exception:
            return None
    if history is None or not history.get("nav_history"):
        return None
    nav_history = history["nav_history"]
    period = period_return_pct(nav_history, span_years)
    if period is None:
        return None
    annual = trailing_cagr(nav_history, span_years)
    if annual is None:
        annual = round(((1 + period / 100.0) ** (1 / span_years) - 1) * 100.0, 2)
    return {
        "scheme": scheme,
        "history": history,
        "score": period,
        "annual_score": annual,
        "has_5y_history": span_years >= 5,
    }


def _span_label(years: int, months: int) -> str:
    parts: list[str] = []
    if years:
        parts.append(f"{years} year" if years == 1 else f"{years} years")
    if months:
        parts.append(f"{months} month" if months == 1 else f"{months} months")
    return " and ".join(parts)


async def _top_funds(sebi_group: str, span_years: float, limit: int = 5) -> list[dict[str, Any]]:
    candidates = await _candidates_for_group(sebi_group, _CANDIDATE_POOL_PER_GROUP)
    if not candidates:
        return []
    results = await asyncio.gather(*(_best_pick(candidate, span_years) for candidate in candidates))
    scored = [result for result in results if result is not None]
    scored.sort(key=lambda result: -result["score"])
    return scored[:limit]


async def _pick_best_fund(sebi_group: str, span_years: float = 5.0) -> dict[str, Any] | None:
    ranked = await _top_funds(sebi_group, span_years, limit=1)
    return ranked[0] if ranked else None


_RANKING_POOL_PER_GROUP = 8
_RANKING_TOTAL = 12


async def rank_funds(risk_profile: str, horizon_years: int, total: int = _RANKING_TOTAL) -> list[dict[str, Any]]:
    """Named Direct-Growth funds for each category of the risk profile's mix, ranked by
    trailing return (5y, else 3y) *within* its category. Slots are split across categories
    by mix weight. Rank 1 is the best performer of the whole list's first category, and the
    numbering continues down the sections, so the list reads as 1..N grouped by category.
    Categories with no synced/scorable funds are skipped."""
    weights = _resolve_risk_weights(horizon_years, risk_profile)

    async def _scored(group: str) -> list[dict[str, Any]]:
        candidates = await _candidates_for_group(group, _RANKING_POOL_PER_GROUP)
        results = await asyncio.gather(*(_best_pick(c) for c in candidates))
        scored = [r for r in results if r is not None]
        scored.sort(key=lambda r: (not r["has_5y_history"], -r["score"]))
        return scored

    per_group = await asyncio.gather(*(_scored(group) for group in weights))
    rows: list[dict[str, Any]] = []
    for (category, weight_pct), scored in zip(weights.items(), per_group, strict=True):
        slots = max(1, round(total * weight_pct / 100.0))
        for pick in scored[:slots]:
            scheme: MutualFundScheme = pick["scheme"]
            rows.append(
                {
                    "category": category,
                    "category_label": CATEGORY_PLAIN_LABELS.get(category, category),
                    "scheme_code": scheme.scheme_code,
                    "scheme_name": scheme.name,
                    "trailing_return_pct": pick["score"],
                    "return_window": "5y" if pick["has_5y_history"] else "3y",
                }
            )
    rows = rows[:total]
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def _fallback_suggestion_explanation(risk_profile: str, horizon_years: int, sleeves: list[dict[str, Any]]) -> str:
    picked = [s["scheme_name"] for s in sleeves if s.get("scheme_name")]
    if not picked:
        return (
            f"No fund data was available to build a {risk_profile} mix for a {horizon_years}-year "
            "horizon right now — the fund master may not have been synced yet."
        )
    names = ", ".join(picked)
    return f"A {risk_profile} mix for a {horizon_years}-year horizon: {names}."


async def _explain_suggestion(risk_profile: str, horizon_years: int, sleeves: list[dict[str, Any]]) -> str:
    try:
        model = get_llm("cheap")
        prompt = (
            "Explain this suggested mutual fund SIP mix in 2-3 plain sentences for someone who has "
            "NEVER invested before and doesn't know any finance terminology. Use ONLY the numbers "
            "and fund names given — do not invent or adjust any figure. Describe each sleeve using "
            "its 'category_label' wording (already plain-English) — never say 'large cap', "
            "'flexi cap', 'mid cap', 'small cap', or 'debt fund' literally. "
            f"Risk profile: {risk_profile}. Horizon: {horizon_years} years. Sleeves: {json.dumps(sleeves)}."
        )
        reply = await model.ainvoke(prompt)
        text = extract_text(reply.content)
        text = text.strip()
        return text or _fallback_suggestion_explanation(risk_profile, horizon_years, sleeves)
    except Exception as exc:
        logger.info("Suggestion explanation model unavailable: %s", exc)
        return _fallback_suggestion_explanation(risk_profile, horizon_years, sleeves)


async def suggest_mix(
    monthly_amount: float,
    horizon_years: int,
    risk_profile: str,
    return_span: str = "quarter",
    span_years: int = 0,
    span_months: int = 0,
) -> dict[str, Any]:
    """Deterministic category weights by horizon/risk, then Direct Growth schemes ranked by
    return over the chosen span. Years and months are that lookback; they are separate from
    how long the user plans to keep the SIP. The top five in each category are returned.
    Expense ratio is not used.
    """
    if span_years or span_months:
        span_length = span_years + span_months / 12
        span_label = _span_label(span_years, span_months)
        span_key = "custom"
    else:
        span_key = return_span if return_span in RETURN_SPANS else "quarter"
        span_length, span_label = RETURN_SPANS[span_key]
    weights = _resolve_risk_weights(horizon_years, risk_profile)
    ranked = await asyncio.gather(*(_top_funds(group, span_length, limit=5) for group in weights))

    sleeves: list[dict[str, Any]] = []
    for (label, weight_pct), picks in zip(weights.items(), ranked, strict=True):
        monthly_inr = round(monthly_amount * weight_pct / 100.0, 2)
        if not picks:
            sleeves.append(
                {
                    "category": label,
                    "category_label": CATEGORY_PLAIN_LABELS.get(label, label),
                    "weight_pct": weight_pct,
                    "monthly_inr": monthly_inr,
                    "status": "DATA_UNAVAILABLE",
                    "scheme_code": None,
                    "scheme_name": None,
                    "funds": [],
                }
            )
            continue
        top = picks[0]
        scheme = top["scheme"]
        projection = project_sip(monthly_inr, horizon_years, top.get("annual_score", top["score"]))
        funds = []
        for pick in picks:
            funds.append(
                {
                    "scheme_code": pick["scheme"].scheme_code,
                    "scheme_name": pick["scheme"].name,
                    "trailing_return_pct_used": pick["score"],
                    "return_window": span_label,
                }
            )
        sleeves.append(
            {
                "category": label,
                "category_label": CATEGORY_PLAIN_LABELS.get(label, label),
                "weight_pct": weight_pct,
                "monthly_inr": monthly_inr,
                "status": "OK",
                "scheme_code": scheme.scheme_code,
                "scheme_name": scheme.name,
                "trailing_return_pct_used": top["score"],
                "return_window": span_label,
                "has_full_5y_history": top["has_5y_history"],
                "projected_corpus": projection["nominal_corpus"],
                "funds": funds,
            }
        )

    explanation = await _explain_suggestion(risk_profile, horizon_years, sleeves)

    return {
        "mode": "suggest",
        "risk_profile": risk_profile,
        "horizon_years": horizon_years,
        "monthly_amount": monthly_amount,
        "return_span": span_key,
        "return_span_label": span_label,
        "sleeves": sleeves,
        "note": (
            f"The first fund in each category had the best Direct Growth return over {span_label}. "
            "Up to five are shown. Expense ratio is not part of the ranking."
        ),
        "explanation": explanation,
    }
