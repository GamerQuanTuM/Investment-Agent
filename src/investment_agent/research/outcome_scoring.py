"""Outcome scoring for logged predictions (Workstream A, Step 8 / Gap 7).

`graph/nodes.py::recommendation_logger_node` writes an immutable `PredictionLog` row
every research run (see `docs/self-correction.md`'s "immutable prediction logs, reality
monitoring" concept), but until this module nothing ever went back and checked what
actually happened — `outcome_status` sat `NULL` forever. This module is that reality
check: a deterministic classification of whether a past prediction's `decision` (did the
screen call this an OPPORTUNITY?) matches what the price actually did once its
`evaluation_due_date` arrives.

This is intentionally simple and auditable: no LLM judges "was this a good call," Python
compares two numbers, same as everywhere else in this codebase.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from investment_agent.db.models.prediction import PredictionLog
from investment_agent.db.session import async_session_factory

logger = logging.getLogger(__name__)

EVALUATION_HORIZON_DAYS = 90


def classify_outcome(decision: str | None, entry_price: float | None, current_price: float | None) -> dict[str, Any]:
    """Pure classification: did the price move the direction the decision implied?

    `OPPORTUNITY` implies the screen expected the price to be worth paying attention to
    going forward — scored CORRECT if the price rose, INCORRECT if it fell, flat (exactly
    0% change) counts as INCORRECT since "worth watching" implied some upside played out.
    `NO_ACTION` made no directional call at all, so there's nothing to score —
    NOT_APPLICABLE, never fabricated as correct or incorrect. Missing prices (fetch
    failed, or this row predates `entry_price` being recorded) are INCONCLUSIVE, not
    silently skipped or guessed.
    """
    if decision not in ("OPPORTUNITY", "NO_ACTION"):
        return {"outcome_status": "INCONCLUSIVE", "evaluation_notes": f"Unrecognized decision value: {decision!r}."}
    if decision == "NO_ACTION":
        return {
            "outcome_status": "NOT_APPLICABLE",
            "evaluation_notes": "Decision was NO_ACTION — no directional call was made to evaluate.",
        }
    if entry_price is None or current_price is None or entry_price <= 0:
        return {
            "outcome_status": "INCONCLUSIVE",
            "evaluation_notes": "Missing entry or current price — this prediction cannot be scored.",
        }

    change_pct = round((current_price - entry_price) / entry_price * 100.0, 2)
    outcome = "CORRECT" if change_pct > 0 else "INCORRECT"
    return {
        "outcome_status": outcome,
        "evaluation_notes": (
            f"Price moved from {entry_price} to {current_price} ({change_pct:+.2f}%) by the "
            f"evaluation date; decision was OPPORTUNITY -> {outcome}."
        ),
    }


async def evaluate_due_predictions() -> dict[str, Any]:
    """Find every `PredictionLog` row past its `evaluation_due_date` with no
    `outcome_status` yet, fetch each one's current price, classify, and write the result
    back. Returns a summary; never raises — a single symbol's price-fetch failure
    classifies that row INCONCLUSIVE and moves on rather than aborting the whole batch."""
    from investment_agent.market.board import quote_for_symbol

    now = datetime.now(UTC)
    evaluated: list[dict[str, Any]] = []

    async with async_session_factory() as session:
        stmt = select(PredictionLog).where(
            PredictionLog.outcome_status.is_(None),
            PredictionLog.evaluation_due_date.is_not(None),
            PredictionLog.evaluation_due_date <= now,
        )
        rows = (await session.scalars(stmt)).all()

        for row in rows:
            entry_price = (row.expected_conditions or {}).get("entry_price")
            decision = (row.expected_conditions or {}).get("decision")
            current_price = None
            try:
                quote = await quote_for_symbol(row.asset_id, "NSE")
                current_price = quote.get("live_price") if quote else None
            except Exception as exc:
                logger.info("Price lookup failed for %s during outcome scoring: %s", row.asset_id, exc)

            result = classify_outcome(decision, entry_price, current_price)
            row.outcome_status = result["outcome_status"]
            row.evaluation_notes = result["evaluation_notes"]
            evaluated.append(
                {
                    "prediction_id": row.prediction_id,
                    "asset_id": row.asset_id,
                    **result,
                }
            )

        await session.commit()

    return {"evaluated_count": len(evaluated), "evaluated": evaluated}
