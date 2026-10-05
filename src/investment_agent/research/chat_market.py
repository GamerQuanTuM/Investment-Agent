"""Chat handlers for "how is the market?" and "how is my portfolio?".

Both only restate data the app already fetches (`/market/indices`, `/market/macro`,
`/market/portfolio/concentration` and `/alerts`). Every figure in the reply is printed
straight from those payloads with its date; a missing piece is reported as DATA_UNAVAILABLE
rather than filled in from model knowledge, and no model writes any of the text.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from investment_agent.research.evidence import Evidence, SourceType

logger = logging.getLogger(__name__)

MARKET_CHIPS = ["Suggest 10 stocks for ₹10,000", "What is an ETF?"]
NO_HOLDINGS_TEXT = (
    "I don't see any holdings yet. Connect your broker (INDstocks) or add your holdings, "
    "then ask again and I'll check how concentrated your portfolio is."
)


def _evidence(**kwargs: Any) -> dict[str, Any]:
    return Evidence(**kwargs).model_dump(mode="json")


def _find(indices: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    return next((i for i in indices if needle in str(i.get("name", "")).lower()), None)


def _index_line(item: dict[str, Any] | None, label: str) -> str:
    if item is None:
        return f"{label}: DATA_UNAVAILABLE"
    return f"{label}: {item['live_price']:,.2f} ({item['day_change_percentage']:+.2f}% today)"


def _mood(nifty: dict[str, Any] | None) -> str:
    if nifty is None:
        return "Market mood: DATA_UNAVAILABLE"
    change = nifty["day_change_percentage"]
    mood = "Risk-on" if change > 0 else "Risk-off" if change < 0 else "Flat"
    return f"Market mood gauge: {mood} (Nifty 50's move today is {change:+.2f}%)"


async def market_overview_reply() -> dict[str, Any]:
    from investment_agent.market.board import live_indices
    from investment_agent.market.macro import get_macro_snapshot

    now = datetime.now(UTC)
    try:
        indices = await live_indices()
    except Exception as exc:
        logger.info("Market overview indices unavailable: %s", exc)
        indices = []
    try:
        macro = await get_macro_snapshot()
    except Exception as exc:
        logger.info("Market overview macro unavailable: %s", exc)
        macro = {}

    if not indices and not any(v.get("status") == "OK" for v in macro.values() if isinstance(v, dict)):
        return {
            "text": "DATA_UNAVAILABLE: I couldn't fetch live market data right now, so I won't describe the market from memory.",
            "needs_input": False,
            "suggestions": list(MARKET_CHIPS),
            "sources": [],
        }

    nifty = _find(indices, "nifty 50")
    vix = next((i for i in indices if "vix" in str(i.get("name", "")).lower()), None)
    lines = [
        f"Market snapshot (fetched {now.date().isoformat()}):",
        _index_line(nifty, "Nifty 50"),
        _index_line(_find(indices, "sensex"), "Sensex"),
        _index_line(vix, "India VIX (fear gauge)") if vix else "India VIX (fear gauge): DATA_UNAVAILABLE (not in our data feed)",
        _mood(nifty),
    ]
    usd = macro.get("usd_inr", {})
    cpi = macro.get("cpi_inflation_yoy", {})
    lines.append(
        f"USD/INR: {usd['value']} (as of {usd.get('data_date')})"
        if usd.get("status") == "OK" and usd.get("value") is not None
        else "USD/INR: DATA_UNAVAILABLE"
    )
    lines.append(
        f"Consumer inflation (year on year): {cpi['value_pct']}% (as of {cpi.get('data_date')})"
        if cpi.get("status") == "OK"
        else "Consumer inflation: DATA_UNAVAILABLE"
    )
    lines.append("These are today's numbers, not a prediction. Educational guidance, not SEBI-registered advice.")

    sources: list[dict[str, Any]] = []
    if indices:
        sources.append(
            _evidence(
                claim="Live index quotes",
                source_name="Yahoo Finance",
                source_url="https://finance.yahoo.com",
                source_type=SourceType.FINANCIAL_DATA_PROVIDER,
                retrieved_at=now,
                data_date=now,
            )
        )
    for item in (usd, cpi):
        if item.get("status") == "OK" and item.get("source_name"):
            sources.append(
                _evidence(
                    claim=str(item.get("source_name")),
                    source_name=str(item.get("source_name")),
                    source_url=str(item.get("source_url") or ""),
                    source_type=SourceType.FRED,
                )
            )
    return {
        "text": "\n".join(lines),
        "needs_input": False,
        "suggestions": list(MARKET_CHIPS),
        "sources": sources,
    }


async def portfolio_help_reply() -> dict[str, Any]:
    from investment_agent.api.routes.market import portfolio
    from investment_agent.research.alerts import generate_portfolio_alerts
    from investment_agent.research.portfolio_insights import build_concentration_report

    try:
        book = await portfolio()
    except Exception as exc:
        logger.info("Portfolio lookup unavailable: %s", exc)
        book = {"holdings": []}
    holdings = book.get("holdings") or []
    if not holdings:
        return {
            "text": NO_HOLDINGS_TEXT,
            "needs_input": False,
            "suggestions": ["Suggest 10 stocks for ₹10,000", "What is diversification?"],
            "sources": [],
        }
    report = build_concentration_report(holdings)
    alerts = generate_portfolio_alerts(holdings)
    lines = [f"I checked your {len(holdings)} holdings."]
    if report["biggest_sector"] is not None:
        lines.append(
            f"Biggest sector: {report['biggest_sector']} at {report['biggest_sector_pct']}%. "
            f"Biggest single holding: {report['biggest_holding_symbol']} at {report['biggest_holding_pct']}%."
        )
        lines.append(f"Diversification score (100 minus your biggest sector's share): {report['diversification_score']}.")
    lines.extend(f"- {alert['message']}" for alert in alerts)
    if not alerts:
        lines.append("Nothing crossed my concentration or drawdown review thresholds.")
    lines.append("This is a check on your own numbers, not an instruction to buy or sell.")
    return {
        "text": "\n".join(lines),
        "needs_input": False,
        "suggestions": ["What is diversification?", "Suggest 10 stocks for ₹10,000"],
        "sources": [
            _evidence(
                claim="Live holdings and prices",
                source_name="INDstocks",
                source_url="https://api.indstocks.com",
                source_type=SourceType.INDSTOCKS,
            )
        ],
    }
