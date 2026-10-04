"""F2 deterministic scoring: Quality, Valuation, Momentum, Risk — each 0-100, plus an
overall weighted score. Pure Python, no I/O, no LLM. Every input that fed a sub-score is
listed alongside it (`inputs`), so the UI can show "ROE 14.2% [source]" next to the number
that produced it, and the LLM (if asked to narrate) only ever sees numbers already computed
here — it cannot invent or adjust a score.

Each `score_*` function returns None for the whole block when there isn't enough data to
score responsibly (fewer than half its inputs available) — a thin, overconfident score built
from one ratio is worse than an honest DATA_UNAVAILABLE. Each input in the `inputs` list is
reported even when its own value is None, so the UI can render "Data unavailable" tiles
rather than silently dropping the row.
"""

from __future__ import annotations

from typing import Any, TypedDict

from investment_agent.portfolio.calculations import calculate_percentile_rank


class ScoreInput(TypedDict):
    label: str
    value: float | None
    unit: str
    benchmark: float | None
    benchmark_label: str | None


class ScoreBlock(TypedDict):
    score: float | None
    inputs: list[ScoreInput]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _linear_score(value: float | None, *, worst: float, best: float) -> float | None:
    """Map `value` linearly onto 0-100 between `worst` (-> 0) and `best` (-> 100).

    `worst` may be greater than `best` (e.g. debt/equity: lower is better, so
    worst=4, best=0). Returns None when `value` is None, never a fabricated midpoint.
    """
    if value is None:
        return None
    if worst == best:
        return 50.0
    pct = (value - worst) / (best - worst)
    return round(_clamp(pct * 100.0), 1)


def _average_available(scores: list[float | None]) -> float | None:
    """Mean of the non-None scores, or None if fewer than half of them are available."""
    available = [s for s in scores if s is not None]
    if len(available) < max(1, len(scores) // 2):
        return None
    return round(sum(available) / len(available), 1)


def score_quality(
    *,
    roe_pct: float | None,
    roce_pct: float | None,
    debt_to_equity: float | None,
    interest_coverage: float | None,
    fcf: float | None,
    revenue_growth_3y_cagr_pct: float | None,
    profit_growth_3y_cagr_pct: float | None,
) -> ScoreBlock:
    """Higher ROE/ROCE/interest-cover/growth and lower debt all raise this score."""
    sub_scores = [
        _linear_score(roe_pct, worst=0, best=25),
        _linear_score(roce_pct, worst=0, best=25),
        _linear_score(debt_to_equity, worst=3, best=0),
        _linear_score(interest_coverage, worst=1, best=10),
        None if fcf is None else (100.0 if fcf > 0 else 0.0),
        _linear_score(revenue_growth_3y_cagr_pct, worst=0, best=20),
        _linear_score(profit_growth_3y_cagr_pct, worst=0, best=20),
    ]
    inputs: list[ScoreInput] = [
        {"label": "Return on equity", "value": roe_pct, "unit": "%", "benchmark": 15.0, "benchmark_label": "quality line"},
        {"label": "Return on capital employed", "value": roce_pct, "unit": "%", "benchmark": 15.0, "benchmark_label": "quality line"},
        {"label": "Debt to equity", "value": debt_to_equity, "unit": "x", "benchmark": 1.0, "benchmark_label": "comfortable ceiling"},
        {"label": "Interest coverage", "value": interest_coverage, "unit": "x", "benchmark": 3.0, "benchmark_label": "safety floor"},
        {"label": "Free cash flow", "value": fcf, "unit": "cr", "benchmark": 0.0, "benchmark_label": "break-even"},
        {"label": "Revenue 3y CAGR", "value": revenue_growth_3y_cagr_pct, "unit": "%", "benchmark": 10.0, "benchmark_label": "healthy growth"},
        {"label": "Profit 3y CAGR", "value": profit_growth_3y_cagr_pct, "unit": "%", "benchmark": 10.0, "benchmark_label": "healthy growth"},
    ]
    return {"score": _average_available(sub_scores), "inputs": inputs}


def score_valuation(
    *,
    pe_ratio: float | None,
    pe_history: list[float] | None,
    pb_ratio: float | None,
    sector_pe_values: list[float] | None,
) -> ScoreBlock:
    """Cheap relative to its own history and to sector peers scores higher.

    Gap 5: `pe_history` is the stock's own trailing P/E over roughly its last 5 years
    (caller derives this from 5y daily closes against a current EPS — see
    `research/stock_score.py` — an approximation when historical EPS isn't available, which
    is flagged in the caller rather than here). `sector_pe_values` is the current P/E of
    other candidates sharing this stock's sector, from our own screened universe. A low
    percentile (cheap vs. history/peers) scores higher — valuation screens reward being
    cheap, unlike quality/momentum where higher is better.
    """
    own_history_percentile = calculate_percentile_rank(pe_ratio, pe_history or []) if pe_ratio is not None else None
    sector_percentile = calculate_percentile_rank(pe_ratio, sector_pe_values or []) if pe_ratio is not None else None

    sub_scores = [
        _linear_score(own_history_percentile, worst=100, best=0),
        _linear_score(sector_percentile, worst=100, best=0),
    ]
    inputs: list[ScoreInput] = [
        {
            "label": "P/E vs. own 5y history",
            "value": own_history_percentile,
            "unit": "pctile",
            "benchmark": 50.0,
            "benchmark_label": "median of own history",
        },
        {
            "label": "P/E vs. sector peers",
            "value": sector_percentile,
            "unit": "pctile",
            "benchmark": 50.0,
            "benchmark_label": "median of sector",
        },
        {"label": "Current P/E", "value": pe_ratio, "unit": "x", "benchmark": None, "benchmark_label": None},
        {"label": "Current P/B", "value": pb_ratio, "unit": "x", "benchmark": None, "benchmark_label": None},
    ]
    return {"score": _average_available(sub_scores), "inputs": inputs}


def score_momentum(
    *,
    return_6m_pct: float | None,
    return_12m_pct: float | None,
    distance_from_52w_high_pct: float | None,
) -> ScoreBlock:
    """Positive trailing returns and sitting close to the 52-week high score higher."""
    sub_scores = [
        _linear_score(return_6m_pct, worst=-20, best=30),
        _linear_score(return_12m_pct, worst=-30, best=50),
        _linear_score(distance_from_52w_high_pct, worst=-40, best=0),
    ]
    inputs: list[ScoreInput] = [
        {"label": "6-month return", "value": return_6m_pct, "unit": "%", "benchmark": 0.0, "benchmark_label": "flat"},
        {"label": "12-month return", "value": return_12m_pct, "unit": "%", "benchmark": 0.0, "benchmark_label": "flat"},
        {
            "label": "Distance from 52-week high",
            "value": distance_from_52w_high_pct,
            "unit": "%",
            "benchmark": 0.0,
            "benchmark_label": "at the high",
        },
    ]
    return {"score": _average_available(sub_scores), "inputs": inputs}


def score_risk(
    *,
    annualized_volatility_pct: float | None,
    max_drawdown_pct: float | None,
    promoter_pledge_pct: float | None,
) -> ScoreBlock:
    """Lower volatility, a shallower drawdown, and no promoter pledge score higher
    (i.e. this is a *safety* score — 100 is low-risk, 0 is high-risk)."""
    sub_scores = [
        _linear_score(annualized_volatility_pct, worst=60, best=10),
        _linear_score(max_drawdown_pct, worst=-60, best=-5),
        _linear_score(promoter_pledge_pct, worst=50, best=0),
    ]
    inputs: list[ScoreInput] = [
        {
            "label": "Annualized volatility",
            "value": annualized_volatility_pct,
            "unit": "%",
            "benchmark": 25.0,
            "benchmark_label": "typical large-cap",
        },
        {
            "label": "Max drawdown (1y)",
            "value": max_drawdown_pct,
            "unit": "%",
            "benchmark": -20.0,
            "benchmark_label": "typical large-cap",
        },
        {
            "label": "Promoter pledge",
            "value": promoter_pledge_pct,
            "unit": "%",
            "benchmark": 0.0,
            "benchmark_label": "no pledge",
        },
    ]
    return {"score": _average_available(sub_scores), "inputs": inputs}


# Overall weighting: quality and valuation matter most for a 3-5 year hold; momentum is a
# minor tilt (this agent is explicitly not a day-trading tool); risk is weighted on par with
# momentum since a single red flag there (e.g. heavy pledge) shouldn't be swamped by a good
# quality score, but also shouldn't dominate it alone.
_OVERALL_WEIGHTS = {"quality": 0.35, "valuation": 0.30, "momentum": 0.15, "risk": 0.20}


def compute_overall_score(
    quality: ScoreBlock, valuation: ScoreBlock, momentum: ScoreBlock, risk: ScoreBlock
) -> float | None:
    """Weighted average of the four sub-scores, renormalized over whichever ones have a
    score — e.g. if valuation is DATA_UNAVAILABLE, its weight is dropped and the other
    three are rescaled to still sum to 1.0, rather than silently treating it as 0."""
    blocks = {"quality": quality, "valuation": valuation, "momentum": momentum, "risk": risk}
    available = {name: block["score"] for name, block in blocks.items() if block["score"] is not None}
    if not available:
        return None
    total_weight = sum(_OVERALL_WEIGHTS[name] for name in available)
    if total_weight <= 0:
        return None
    weighted = sum(available[name] * _OVERALL_WEIGHTS[name] for name in available)
    return round(weighted / total_weight, 1)


def build_score_card(
    *,
    quality_inputs: dict[str, Any],
    valuation_inputs: dict[str, Any],
    momentum_inputs: dict[str, Any],
    risk_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Convenience wrapper: build all four blocks + overall from keyword-arg dicts, so
    callers (the API route) can assemble inputs once and get the full card back."""
    quality = score_quality(**quality_inputs)
    valuation = score_valuation(**valuation_inputs)
    momentum = score_momentum(**momentum_inputs)
    risk = score_risk(**risk_inputs)
    overall = compute_overall_score(quality, valuation, momentum, risk)
    return {
        "quality": quality,
        "valuation": valuation,
        "momentum": momentum,
        "risk": risk,
        "overall": overall,
    }
