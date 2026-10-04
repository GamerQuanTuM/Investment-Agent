"""Deterministic portfolio alerts (Workstream A, Step 8 / F8).

Every alert here follows from a plain arithmetic threshold check over a holding's own
already-fetched numbers (`GET /market/portfolio`) and the concentration report from
`research/portfolio_insights.py` — no LLM call, no day-trading signal (no "buy now"/
"sell now" instruction), consistent with this project's hard rules. These are the same
kind of "worth a human look" flags Gap 8's concentration flags are, just scoped per
holding instead of portfolio-wide.
"""

from __future__ import annotations

from typing import Any

from investment_agent.research.portfolio_insights import (
    SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT,
    build_concentration_report,
)

DRAWDOWN_ALERT_THRESHOLD_PCT = -15.0


def generate_portfolio_alerts(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One alert per holding/condition that crosses a threshold. Each alert states the
    exact numbers behind it so nothing reads as an opaque AI judgment."""
    alerts: list[dict[str, Any]] = []

    for holding in holdings:
        symbol = holding.get("symbol")
        pnl_pct = holding.get("unrealized_pnl_pct")
        if pnl_pct is not None and pnl_pct <= DRAWDOWN_ALERT_THRESHOLD_PCT:
            alerts.append(
                {
                    "symbol": symbol,
                    "severity": "WARNING",
                    "kind": "DRAWDOWN",
                    "message": (
                        f"{symbol} is down {pnl_pct}% from your average buy price "
                        f"(below the {DRAWDOWN_ALERT_THRESHOLD_PCT}% review threshold)."
                    ),
                }
            )

        allocation_pct = holding.get("allocation_pct")
        if allocation_pct is not None and allocation_pct > SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT:
            alerts.append(
                {
                    "symbol": symbol,
                    "severity": "INFO",
                    "kind": "CONCENTRATION",
                    "message": (
                        f"{symbol} is {allocation_pct}% of your portfolio "
                        f"(above the {SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT}% single-holding threshold)."
                    ),
                }
            )

    concentration = build_concentration_report(holdings)
    for flag in concentration["concentration_flags"]:
        # Skip a sector flag that's already fully explained by a single holding's own
        # alert above (common when one stock *is* most of its sector in this portfolio) —
        # avoids showing two alerts that say almost the same thing.
        if not any(a["kind"] == "CONCENTRATION" and a["symbol"] in flag for a in alerts):
            alerts.append({"symbol": None, "severity": "INFO", "kind": "SECTOR_CONCENTRATION", "message": flag})

    return alerts
