"""Portfolio concentration analysis (Workstream A, Step 7 / Gap 8).

The README's own stated scope for "Layer B" says the personal agent evaluates
recommendations against "the user's risk profile, monthly budget, **existing portfolio
concentration**, and investment horizon" — but until this module, nothing in the
codebase actually computed or surfaced that concentration. `portfolio/calculations.py`
already had `calculate_sector_exposure`; this is the first caller of it outside the
research graph's internal risk node.

Pure Python over an already-fetched holdings list (the same shape
`GET /market/portfolio` already returns) — no I/O, no LLM. Thresholds are module-level
constants, the single auditable place to tune them.
"""

from __future__ import annotations

from typing import Any

from investment_agent.portfolio.calculations import calculate_sector_exposure

SECTOR_CONCENTRATION_THRESHOLD_PCT = 30.0
SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT = 20.0


def build_concentration_report(holdings: list[dict[str, Any]]) -> dict[str, Any]:
    """Sector exposure breakdown, the single biggest position, and plain-language flags
    when either crosses its threshold. `None`/empty fields (never a fabricated 0) when
    there are no holdings to analyze."""
    if not holdings:
        return {
            "sector_exposure_pct": {},
            "biggest_sector": None,
            "biggest_sector_pct": None,
            "biggest_holding_symbol": None,
            "biggest_holding_pct": None,
            "diversification_score": None,
            "concentration_flags": [],
        }

    sector_exposure = calculate_sector_exposure(
        [{"sector": h.get("sector", "Unclassified"), "market_value": h.get("current_value", 0.0)} for h in holdings]
    )
    biggest_sector_item = max(sector_exposure.items(), key=lambda kv: kv[1]) if sector_exposure else None
    biggest_holding = max(holdings, key=lambda h: float(h.get("allocation_pct") or 0.0))

    flags: list[str] = []
    if biggest_sector_item and biggest_sector_item[1] > SECTOR_CONCENTRATION_THRESHOLD_PCT:
        flags.append(
            f"{biggest_sector_item[0]} is {biggest_sector_item[1]}% of your portfolio — above the "
            f"{SECTOR_CONCENTRATION_THRESHOLD_PCT}% sector-concentration threshold."
        )
    biggest_holding_pct = float(biggest_holding.get("allocation_pct") or 0.0)
    if biggest_holding_pct > SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT:
        flags.append(
            f"{biggest_holding.get('symbol')} alone is {biggest_holding_pct}% of your portfolio — above the "
            f"{SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT}% single-holding threshold."
        )

    # Simple, documented diversification score: 100 minus the single biggest sector's
    # share. A portfolio spread evenly across many sectors scores near 100; one sector
    # dominating the book pulls it down toward 0. Deliberately not a Herfindahl-style
    # index (more "correct" statistically, but harder to explain in the UI for no real
    # gain here) — if that precision is ever needed, swap the formula here, the input
    # contract (sector_exposure_pct) stays the same.
    diversification_score = round(max(0.0, 100.0 - (biggest_sector_item[1] if biggest_sector_item else 0.0)), 2)

    return {
        "sector_exposure_pct": sector_exposure,
        "biggest_sector": biggest_sector_item[0] if biggest_sector_item else None,
        "biggest_sector_pct": biggest_sector_item[1] if biggest_sector_item else None,
        "biggest_holding_symbol": biggest_holding.get("symbol"),
        "biggest_holding_pct": biggest_holding_pct,
        "diversification_score": diversification_score,
        "concentration_flags": flags,
    }
