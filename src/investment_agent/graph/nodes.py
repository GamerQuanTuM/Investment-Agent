import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from investment_agent.config.settings import get_settings
from investment_agent.db.models.prediction import PredictionLog
from investment_agent.db.session import async_session_factory
from investment_agent.graph.state import InvestmentGraphState
from investment_agent.market.news import get_news
from investment_agent.market.nse import get_filings
from investment_agent.market.universe import (
    load_candidates_from_db,
    load_portfolio_from_broker,
    load_user_profile_from_db,
)
from investment_agent.portfolio.calculations import calculate_sector_exposure
from investment_agent.research.evidence import SourceType
from investment_agent.research.outcome_scoring import EVALUATION_HORIZON_DAYS
from investment_agent.research.sentiment import aggregate_sentiment

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_fresh(timestamp: str | None, max_age_hours: int) -> bool:
    if not timestamp:
        return False
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return datetime.now(UTC) - parsed <= timedelta(hours=max_age_hours)


# ---------------------------------------------------------------------------
# Node 1: Load User Profile
# ---------------------------------------------------------------------------
async def load_user_profile_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Load a stored risk profile. Request budget is used when no profile row exists."""
    user_id = state.get("user_id", "default_user")
    warnings = list(state.get("warnings", []))
    profile = state.get("user_profile")
    if profile is None:
        profile = await load_user_profile_from_db(user_id)
    if profile is None:
        warnings.append(
            "User profile not found in the database. Using the request budget and default allocation caps."
        )
        profile = {
            "user_id": user_id,
            "risk_tolerance": "moderate",
            "investment_horizon_years": 5,
            "monthly_budget": state.get("monthly_budget", 0.0),
            "max_single_stock_allocation_pct": 15.0,
            "max_sector_allocation_pct": 25.0,
            "financial_goal": "Long-term wealth accumulation",
            "profile_source": "request_defaults",
        }
    monthly_budget = float(profile.get("monthly_budget") or state.get("monthly_budget") or 0.0)
    if state.get("monthly_budget"):
        monthly_budget = float(state["monthly_budget"])
        profile = {**profile, "monthly_budget": monthly_budget}
    logger.info(
        "Loaded user profile for %s from %s", user_id, profile.get("profile_source", "state")
    )
    return {
        "user_profile": profile,
        "monthly_budget": monthly_budget,
        "errors": state.get("errors", []),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Node 2: Load Portfolio
# ---------------------------------------------------------------------------
async def load_portfolio_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Load holdings from INDstocks. An explicit portfolio on the request is kept."""
    warnings = list(state.get("warnings", []))
    if state.get("portfolio"):
        return {"portfolio": state["portfolio"], "warnings": warnings}

    portfolio = None
    try:
        portfolio = await load_portfolio_from_broker()
    except Exception as exc:
        warnings.append(f"INDstocks portfolio lookup failed: {exc}")
        logger.info("Portfolio lookup failed: %s", exc)

    if portfolio is None:
        warnings.append("Portfolio DATA_UNAVAILABLE. INDstocks holdings were not loaded.")
        portfolio = {
            "cash_available": 0.0,
            "total_value": 0.0,
            "holdings": [],
            "sector_allocations": {},
            "portfolio_source": "unavailable",
        }
    else:
        holdings = portfolio.get("holdings", [])
        portfolio["sector_allocations"] = calculate_sector_exposure(
            [
                {
                    "sector": h.get("sector", "Unclassified"),
                    "market_value": h.get("market_value", 0.0),
                }
                for h in holdings
            ]
        )
    logger.info("Loaded portfolio source=%s", portfolio.get("portfolio_source"))
    return {"portfolio": portfolio, "warnings": warnings}


# ---------------------------------------------------------------------------
# Node 3: Load Research Universe
# ---------------------------------------------------------------------------
async def load_research_universe_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Load candidates supplied on the request, otherwise the latest stored snapshots."""
    warnings = list(state.get("warnings", []))
    existing_candidates = state.get("candidates")
    if existing_candidates is not None:
        return {"candidates": existing_candidates, "warnings": warnings}

    candidates = await load_candidates_from_db()
    if not candidates:
        warnings.append(
            "Research universe DATA_UNAVAILABLE. Refresh INDstocks prices and submit sourced fundamentals."
        )
    logger.info("Loaded research universe with %s assets", len(candidates))
    return {"candidates": candidates, "warnings": warnings}


# ---------------------------------------------------------------------------
# Node 4: Market Data Validation
# ---------------------------------------------------------------------------
async def market_data_validation_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Drop names that lack a fresh price or the ratios the screen requires."""
    settings = get_settings()
    candidates = state.get("candidates", [])
    valid_candidates = []
    warnings = list(state.get("warnings", []))
    errors = list(state.get("errors", []))

    for candidate in candidates:
        symbol = candidate.get("symbol", "UNKNOWN")
        if not candidate.get("has_price_data") or float(candidate.get("current_price") or 0) <= 0:
            warnings.append(f"Excluded {symbol}: DATA_UNAVAILABLE for market price")
            continue
        price_time = candidate.get("price_retrieved_at")
        if not _is_fresh(price_time, settings.MARKET_DATA_MAX_AGE_HOURS):
            warnings.append(f"Excluded {symbol}: market price is missing a fresh timestamp")
            continue
        if candidate.get("pe_ratio") is None or candidate.get("roe_pct") is None:
            warnings.append(f"Excluded {symbol}: INSUFFICIENT_EVIDENCE for essential ratios")
            continue
        if not candidate.get("source_url") or not candidate.get("source_name"):
            warnings.append(f"Excluded {symbol}: fundamentals have no source URL")
            continue
        valid_candidates.append(candidate)

    market_context = state.get("market_context") or {"validation_time": utc_now_iso()}
    market_context.setdefault("validation_time", utc_now_iso())

    return {
        "candidates": valid_candidates,
        "market_context": market_context,
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Node 5: Candidate Screening (Deterministic Filters)
# ---------------------------------------------------------------------------
async def candidate_screening_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Deterministic screening: filter candidates based on liquidity, debt, and quality."""
    candidates = state.get("candidates", [])
    screened: list[dict[str, Any]] = []
    warnings = list(state.get("warnings", []))

    for candidate in candidates:
        symbol = candidate.get("symbol")
        if float(candidate.get("promoter_pledge_pct") or 0.0) > 15.0:
            warnings.append(
                f"Filtered out {symbol}: high promoter pledge ({candidate.get('promoter_pledge_pct')}%)"
            )
            continue

        is_financial = candidate.get("sector") == "Financial Services"
        if not is_financial and float(candidate.get("debt_to_equity") or 0.0) > 2.0:
            warnings.append(
                f"Filtered out {symbol}: high debt-to-equity ({candidate.get('debt_to_equity')})"
            )
            continue

        if float(candidate.get("roe_pct") or 0.0) < 12.0:
            warnings.append(
                f"Filtered out {symbol}: ROE ({candidate.get('roe_pct')}%) below quality threshold"
            )
            continue

        screened.append(candidate)

    logger.info("Candidate screening: %s of %s passed filters", len(screened), len(candidates))
    return {"candidates": screened, "warnings": warnings}


def _evidence(candidate: dict[str, Any], claim: str, *, price: bool = False) -> dict[str, Any]:
    if price:
        return {
            "claim": claim,
            "source_name": candidate.get("price_source_name") or "INDstocks",
            "source_url": candidate.get("price_source_url") or "",
            "source_type": SourceType.INDSTOCKS.value,
            "confidence": 1.0,
            "retrieved_at": candidate.get("price_retrieved_at") or utc_now_iso(),
            "data_date": candidate.get("price_retrieved_at"),
        }
    return {
        "claim": claim,
        "source_name": candidate.get("source_name"),
        "source_url": candidate.get("source_url") or "",
        "source_type": candidate.get("source_type") or SourceType.COMPANY_FILING.value,
        "confidence": 1.0,
        "retrieved_at": utc_now_iso(),
        "data_date": candidate.get("data_date"),
    }


# ---------------------------------------------------------------------------
# Node 6: Fundamental Analysis Agent
# ---------------------------------------------------------------------------
async def fundamental_analysis_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Record fundamental facts that already carry a source. No ratios are invented here."""
    candidates = state.get("candidates", [])
    evidence_list = list(state.get("evidence", []))
    analysis: dict[str, Any] = {}

    for candidate in candidates:
        symbol = str(candidate.get("symbol", "UNKNOWN"))
        roe = candidate.get("roe_pct")
        analysis[symbol] = {
            "symbol": symbol,
            "revenue_cagr_3y": candidate.get("revenue_growth_3y_cagr_pct"),
            "profit_cagr_3y": candidate.get("profit_growth_3y_cagr_pct"),
            "roe": roe,
            "roce": candidate.get("roce_pct"),
            "debt_to_equity": candidate.get("debt_to_equity"),
            "quality_tier": "HIGH" if float(roe or 0) > 20 else "MODERATE",
        }
        evidence_list.append(
            _evidence(
                candidate,
                (
                    f"{symbol} ROE {candidate.get('roe_pct')}%, ROCE {candidate.get('roce_pct')}%, "
                    f"debt/equity {candidate.get('debt_to_equity')}, "
                    f"promoter pledge {candidate.get('promoter_pledge_pct')}%"
                ),
            )
        )

    return {"fundamental_analysis": analysis, "evidence": evidence_list}


# ---------------------------------------------------------------------------
# Node 7: News & Announcements Analysis
# ---------------------------------------------------------------------------
_FILING_RISK_KEYWORDS = (
    "resignation",
    "resign",
    "default",
    "winding up",
    "insolvency",
    "investigation",
    "raid",
    "fraud",
    "suspension",
    "delisting",
    "strike",
)


async def news_analysis_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Fetch live NSE corporate announcements (F1) and real news headlines (F4) per
    candidate, concurrently.

    `filings_risk` is a keyword heuristic over real exchange filings. `sentiment_label`
    (F4) is a separate, broader lexicon score over real news headlines (`market/news.py`
    + `research/sentiment.py`) — still deterministic Python, never an LLM/ML classifier,
    per this project's "Python computes every number" rule. The two are combined into a
    single `news_risk` that `risk_agent_node` reads: ELEVATED if either signal is
    elevated/negative, DATA_UNAVAILABLE only if *both* signals are unavailable, else
    NORMAL. A blocked/unavailable source degrades its own half to DATA_UNAVAILABLE
    instead of failing the run (see market/nse.py, market/news.py).
    """
    candidates = state.get("candidates", [])
    symbols = [str(candidate.get("symbol", "UNKNOWN")) for candidate in candidates]
    news_query_by_symbol = {
        str(candidate.get("symbol", "UNKNOWN")): str(candidate.get("name") or candidate.get("symbol", "UNKNOWN"))
        for candidate in candidates
    }
    news_summary: dict[str, Any] = {}

    async def _filings_or_empty(symbol: str) -> list[dict[str, Any]]:
        # Belt-and-suspenders on top of nse.py's own cooldown: a single candidate's NSE
        # call must never be allowed to stall this node past a few seconds, regardless of
        # how many candidates are in the universe.
        try:
            return await asyncio.wait_for(get_filings(symbol), timeout=10.0)
        except TimeoutError:
            return []

    async def _news_or_empty(query: str) -> list[dict[str, Any]]:
        try:
            return await asyncio.wait_for(get_news(f"{query} stock NSE"), timeout=10.0)
        except TimeoutError:
            return []

    if symbols:
        filings_results, news_results = await asyncio.gather(
            asyncio.gather(*(_filings_or_empty(symbol) for symbol in symbols)),
            asyncio.gather(*(_news_or_empty(news_query_by_symbol[symbol]) for symbol in symbols)),
        )
        filings_by_symbol = dict(zip(symbols, filings_results, strict=True))
        news_by_symbol = dict(zip(symbols, news_results, strict=True))
    else:
        filings_by_symbol = {}
        news_by_symbol = {}

    for symbol in symbols:
        filings = filings_by_symbol.get(symbol) or []
        flagged = [
            item["subject"]
            for item in filings
            if any(keyword in (item.get("subject") or "").lower() for keyword in _FILING_RISK_KEYWORDS)
        ]
        filings_risk = "DATA_UNAVAILABLE" if not filings else ("ELEVATED" if flagged else "NORMAL")

        articles = news_by_symbol.get(symbol) or []
        sentiment = aggregate_sentiment(articles)

        if filings_risk == "DATA_UNAVAILABLE" and sentiment["label"] == "DATA_UNAVAILABLE":
            news_risk = "DATA_UNAVAILABLE"
        elif filings_risk == "ELEVATED" or sentiment["label"] == "NEGATIVE":
            news_risk = "ELEVATED"
        else:
            news_risk = "NORMAL"

        news_summary[symbol] = {
            "recent_announcements": [item["subject"] for item in filings[:5]] if filings else "DATA_UNAVAILABLE",
            "filings_risk": filings_risk,
            "flagged_filings": flagged,
            "source_url": filings[0].get("source_url") if filings else None,
            "articles": articles[:5],
            "sentiment_label": sentiment["label"],
            "sentiment_score": sentiment["score"],
            "sentiment_positive_count": sentiment["positive_count"],
            "sentiment_negative_count": sentiment["negative_count"],
            "news_risk": news_risk,
        }

    return {"market_context": {**state.get("market_context", {}), "news_summary": news_summary}}


# ---------------------------------------------------------------------------
# Node 8: Valuation Analysis Agent
# ---------------------------------------------------------------------------
async def valuation_analysis_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Record P/E from the candidate. A sector median is included only when supplied."""
    candidates = state.get("candidates", [])
    valuations: dict[str, Any] = {}
    evidence_list = list(state.get("evidence", []))

    for candidate in candidates:
        symbol = str(candidate.get("symbol", "UNKNOWN"))
        pe = candidate.get("pe_ratio")
        benchmark = candidate.get("sector_median_pe")
        valuations[symbol] = {
            "current_pe": pe,
            "benchmark_pe": benchmark,
            "valuation_status": "DATA_UNAVAILABLE" if benchmark is None else "RELATIVE",
        }
        evidence_list.append(
            _evidence(
                candidate,
                f"{symbol} price {candidate.get('current_price')} and P/E {pe}",
                price=True,
            )
        )

    return {"valuation_analysis": valuations, "evidence": evidence_list}


# ---------------------------------------------------------------------------
# Node 9: Risk Agent
# ---------------------------------------------------------------------------
async def risk_agent_node(state: InvestmentGraphState) -> dict[str, Any]:
    """State risks that follow from the stored ratios, plus the combined `news_risk`
    (filings keyword screen + F4 news sentiment) from news_analysis_node instead of a
    hardcoded DATA_UNAVAILABLE."""
    candidates = state.get("candidates", [])
    risks: dict[str, Any] = {}
    news_summary = state.get("market_context", {}).get("news_summary", {})

    for candidate in candidates:
        symbol = str(candidate.get("symbol", "UNKNOWN"))
        pledge = float(candidate.get("promoter_pledge_pct") or 0)
        debt = float(candidate.get("debt_to_equity") or 0)
        risks[symbol] = {
            "promoter_pledge_pct": pledge,
            "debt_to_equity": debt,
            "financial_risk": "ELEVATED" if debt > 1 else "LOW",
            "governance_flag": "PLEDGE_PRESENT" if pledge > 0 else "NO_PLEDGE_IN_SNAPSHOT",
            "news_risk": news_summary.get(symbol, {}).get("news_risk", "DATA_UNAVAILABLE"),
        }

    return {"risk_analysis": risks}


# ---------------------------------------------------------------------------
# Node 10: Bull Case Agent
# ---------------------------------------------------------------------------
async def bull_case_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Restate the stored growth and profitability facts as the bull case."""
    candidates = state.get("candidates", [])
    bull_cases: dict[str, Any] = {}

    for candidate in candidates:
        symbol = str(candidate.get("symbol", "UNKNOWN"))
        bull_cases[symbol] = {
            "thesis": [
                f"ROE in the sourced snapshot is {candidate.get('roe_pct')}%",
                f"3Y profit CAGR in the sourced snapshot is {candidate.get('profit_growth_3y_cagr_pct')}%",
            ],
            "supporting_evidence": [candidate.get("source_url")],
            "assumptions": [
                "The sourced ratios remain representative over a 3-5 year holding period",
            ],
        }

    return {"bull_case": bull_cases}


# ---------------------------------------------------------------------------
# Node 11: Bear Case Agent
# ---------------------------------------------------------------------------
async def bear_case_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Record the conditions that would break the sourced thesis."""
    candidates = state.get("candidates", [])
    bear_cases: dict[str, Any] = {}

    for candidate in candidates:
        symbol = str(candidate.get("symbol", "UNKNOWN"))
        bear_cases[symbol] = {
            "counterarguments": [
                "Quarterly filings after this snapshot can reverse the growth and ROE figures",
            ],
            "negative_evidence": [],
            "thesis_break_conditions": [
                "ROE in a later filing falls below 12%",
                "Promoter pledge in a later filing rises above 15%",
                "Debt to equity for a non-financial company rises above 2",
            ],
        }

    return {"bear_case": bear_cases}


# ---------------------------------------------------------------------------
# Node 12: Portfolio Impact Agent
# ---------------------------------------------------------------------------
async def portfolio_impact_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Check concentration against the live book. An empty book does not block the first SIP."""
    candidates = state.get("candidates", [])
    user_profile = state.get("user_profile", {})
    portfolio = state.get("portfolio", {})
    max_single_stock = float(user_profile.get("max_single_stock_allocation_pct", 15.0))
    max_sector = float(user_profile.get("max_sector_allocation_pct", 25.0))
    monthly_budget = float(state.get("monthly_budget") or 0.0)
    total_value = float(portfolio.get("total_value") or 0.0)
    holdings = portfolio.get("holdings") or []
    held_value = {
        str(item.get("symbol", "")).upper(): float(item.get("market_value") or 0.0)
        for item in holdings
    }
    sector_value: dict[str, float] = {}
    for item in holdings:
        sector = str(item.get("sector") or "Unclassified")
        sector_value[sector] = sector_value.get(sector, 0.0) + float(
            item.get("market_value") or 0.0
        )

    impact: dict[str, Any] = {}
    for candidate in candidates:
        symbol = str(candidate.get("symbol", "UNKNOWN"))
        sector = str(candidate.get("sector") or "Unclassified")
        if total_value <= 0:
            within = True
            projected = None
            proposed = monthly_budget
        else:
            projected_book = total_value + monthly_budget
            projected = round(
                ((held_value.get(symbol.upper(), 0.0) + monthly_budget) / projected_book) * 100.0,
                2,
            )
            sector_projected = round(
                ((sector_value.get(sector, 0.0) + monthly_budget) / projected_book) * 100.0,
                2,
            )
            within = projected <= max_single_stock and sector_projected <= max_sector
            proposed = monthly_budget if within else 0.0
        impact[symbol] = {
            "projected_weight_pct": projected,
            "max_allowed_pct": max_single_stock,
            "within_limits": within,
            "proposed_sip_monthly": proposed,
        }

    return {"portfolio_impact": impact}


# ---------------------------------------------------------------------------
# Node 13: Evidence Verifier
# ---------------------------------------------------------------------------
async def evidence_verifier_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Accept a claim only when it names a source URL."""
    candidates = state.get("candidates", [])
    evidence = state.get("evidence", [])
    contradictions = list(state.get("contradictions", []))

    if not candidates:
        return {
            "evidence_quality": "NO_CANDIDATES",
            "confidence": 0.0,
            "execution_status": "INSUFFICIENT_EVIDENCE",
        }

    if not evidence:
        return {
            "evidence_quality": "INSUFFICIENT_EVIDENCE",
            "confidence": 0.0,
            "contradictions": ["No verified primary or secondary evidence entries recorded."],
            "execution_status": "INSUFFICIENT_EVIDENCE",
        }

    for candidate in candidates:
        symbol = candidate.get("symbol")
        matched = [
            item
            for item in evidence
            if symbol in item.get("claim", "")
            and item.get("source_url")
            and item.get("source_name")
        ]
        if not matched:
            return {
                "evidence_quality": "INSUFFICIENT_EVIDENCE",
                "confidence": 0.0,
                "contradictions": [f"Missing sourced evidence for {symbol}"],
                "execution_status": "INSUFFICIENT_EVIDENCE",
            }

    return {
        "evidence_quality": "SOURCED",
        "confidence": 0.7,
        "contradictions": contradictions,
        "execution_status": "VERIFIED",
    }


# ---------------------------------------------------------------------------
# Node 14: Recommendation Gate
# ---------------------------------------------------------------------------
async def recommendation_gate_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Opportunity only when evidence passed and the SIP fits the concentration cap."""
    status = state.get("execution_status")
    candidates = state.get("candidates", [])
    impact = state.get("portfolio_impact", {})

    if status == "INSUFFICIENT_EVIDENCE" or not candidates:
        return {
            "execution_status": "INSUFFICIENT_EVIDENCE",
            "recommendation": {
                "decision": "NO_ACTION",
                "reason": "Insufficient verified evidence or no candidates passed deterministic screening.",
                "status": "INSUFFICIENT_EVIDENCE",
                "action_items": [],
            },
        }

    selected = max(candidates, key=lambda item: float(item.get("roe_pct") or 0))
    symbol = str(selected.get("symbol"))
    symbol_impact = impact.get(symbol, {})
    proposed_amt = float(symbol_impact.get("proposed_sip_monthly") or 0)
    if not symbol_impact.get("within_limits", False) or proposed_amt <= 0:
        return {
            "recommendation": {
                "decision": "NO_ACTION",
                "asset_id": symbol,
                "reason": "Candidate passed screening but the SIP would breach a concentration cap or the budget is zero.",
                "status": "NO_ACTION",
                "action_items": [],
            }
        }

    return {
        "recommendation": {
            "decision": "OPPORTUNITY",
            "asset_id": symbol,
            "name": selected.get("name"),
            "proposed_monthly_allocation": proposed_amt,
            "horizon_years": state.get("user_profile", {}).get("investment_horizon_years", 5),
            "action_items": [
                f"Consider a SIP of ₹{proposed_amt:,.0f}/month in {symbol} if the next filing still meets the screen.",
                "Re-check ROE, pledge, and debt when the next quarterly result is published.",
            ],
            "status": "CONSIDER",
        }
    }


# ---------------------------------------------------------------------------
# Node 15: Investment Report
# ---------------------------------------------------------------------------
async def investment_report_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Separate stored facts from the screen's interpretation."""
    rec = state.get("recommendation", {})
    candidates = state.get("candidates", [])
    selected_symbol = rec.get("asset_id")
    primary = next((item for item in candidates if item.get("symbol") == selected_symbol), None)
    if primary is None and candidates:
        primary = candidates[0]
    primary = primary or {}
    symbol = primary.get("symbol", "N/A")
    fundamentals = state.get("fundamental_analysis", {}).get(symbol, {})
    risks = state.get("risk_analysis", {}).get(symbol, {})
    news = state.get("market_context", {}).get("news_summary", {}).get(symbol, {})
    filings_risk = news.get("filings_risk", "DATA_UNAVAILABLE")
    if filings_risk == "DATA_UNAVAILABLE":
        uncertainty = ["Corporate announcements: DATA_UNAVAILABLE — NSE filings could not be fetched for this run."]
    elif filings_risk == "ELEVATED":
        uncertainty = [
            "Corporate announcements flagged at least one recent filing worth reading in full: "
            + "; ".join(news.get("flagged_filings") or []) or "see /market/stocks/{symbol}/filings."
        ]
    else:
        uncertainty = ["Corporate announcements: no recent filing matched the risk-keyword screen."]

    sentiment_label = news.get("sentiment_label", "DATA_UNAVAILABLE")
    if sentiment_label == "DATA_UNAVAILABLE":
        uncertainty.append("Recent news sentiment: DATA_UNAVAILABLE — no news headlines could be fetched for this run.")
    else:
        uncertainty.append(
            f"Recent news sentiment: {sentiment_label} (a keyword-lexicon score over "
            f"{news.get('sentiment_positive_count', 0)} positive vs. "
            f"{news.get('sentiment_negative_count', 0)} negative headline matches out of "
            f"{len(news.get('articles') or [])} articles — not an AI/NLP sentiment model)."
        )

    report = {
        "title": f"Investment Research Brief: {primary.get('name', symbol)}",
        "date": utc_now_iso(),
        "decision": rec.get("decision", "NO_ACTION"),
        "FACT": [
            f"Current price: {primary.get('current_price')}",
            f"P/E: {primary.get('pe_ratio')}",
            f"ROE: {primary.get('roe_pct')}%",
            f"Debt to equity: {primary.get('debt_to_equity')}",
            f"Promoter pledge: {primary.get('promoter_pledge_pct')}%",
            f"Fundamental source: {primary.get('source_name')} {primary.get('source_url')}",
        ],
        "INTERPRETATION": [
            f"Quality tier from the ROE screen: {fundamentals.get('quality_tier', 'DATA_UNAVAILABLE')}",
            f"Financial risk from debt/equity: {risks.get('financial_risk', 'DATA_UNAVAILABLE')}",
        ],
        "ASSUMPTION": [
            "The holding horizon is the horizon on the user profile.",
            "Ratios in the snapshot stay representative until the next filing.",
        ],
        "UNCERTAINTY": uncertainty,
        "RISK": [
            f"Promoter pledge {primary.get('promoter_pledge_pct')}%",
            f"Debt to equity {primary.get('debt_to_equity')}",
        ],
        "EVIDENCE_SOURCES": [
            {"source_name": item.get("source_name"), "source_url": item.get("source_url")}
            for item in state.get("evidence", [])
        ],
    }

    return {"recommendation": {**rec, "report": report}}


# ---------------------------------------------------------------------------
# Node 16: Recommendation Logger
# ---------------------------------------------------------------------------
async def recommendation_logger_node(state: InvestmentGraphState) -> dict[str, Any]:
    """Persist the decision when Postgres is reachable. The response still returns the
    log entry.

    Stores `entry_price` (the candidate's price at prediction time) and
    `evaluation_due_date` (now + `EVALUATION_HORIZON_DAYS`) inside `expected_conditions` —
    previously neither was recorded, which meant Gap 7's outcome scoring (see
    `research/outcome_scoring.py`) would have had no reference price to compare against
    later and no way to know when a prediction was due for review.
    """
    rec = state.get("recommendation", {})
    settings = get_settings()
    pred_id = f"pred_{uuid.uuid4().hex[:12]}"
    asset_id = rec.get("asset_id") or "N/A"
    candidates = state.get("candidates", [])
    primary = next((c for c in candidates if c.get("symbol") == asset_id), None)
    entry_price = (primary or {}).get("current_price")
    due_date = datetime.now(UTC) + timedelta(days=EVALUATION_HORIZON_DAYS)
    log_entry = {
        "prediction_id": pred_id,
        "asset_id": asset_id,
        "created_at": utc_now_iso(),
        "decision": rec.get("decision"),
        "confidence": state.get("confidence", 0.0),
        "prompt_version": "v1.1.0",
        "strategy_version": "1.1.0",
        "persisted": False,
    }
    try:
        async with async_session_factory() as session:
            session.add(
                PredictionLog(
                    prediction_id=pred_id,
                    asset_id=str(asset_id),
                    user_id=state.get("user_id"),
                    thesis=str(rec.get("reason") or rec.get("decision") or "NO_ACTION"),
                    assumptions=[],
                    expected_conditions={
                        "action_items": rec.get("action_items") or [],
                        "entry_price": entry_price,
                        "decision": rec.get("decision"),
                    },
                    evidence_ids=[],
                    confidence=float(state.get("confidence") or 0.0),
                    status=str(rec.get("status") or "NO_ACTION"),
                    model_provider=settings.PRIMARY_LLM_PROVIDER,
                    model_name=settings.PRIMARY_LLM_MODEL,
                    prompt_version="v1.1.0",
                    strategy_version="1.1.0",
                    evaluation_due_date=due_date,
                )
            )
            await session.commit()
            log_entry["persisted"] = True
    except Exception:
        logger.info("Prediction %s was not persisted", pred_id)
    return {"recommendation": {**rec, "log_entry": log_entry}}
