from typing import Any

from typing_extensions import TypedDict


class InvestmentGraphState(TypedDict, total=False):
    """Strongly typed LangGraph state for the Indian market investment research & guidance agent."""

    # User & portfolio context (Layer B)
    user_id: str
    user_profile: dict[str, Any]
    portfolio: dict[str, Any]
    monthly_budget: float

    # Research & market universe (Layer A)
    market_context: dict[str, Any]
    candidates: list[dict[str, Any]]
    research_documents: list[dict[str, Any]]

    # Agent analysis results
    fundamental_analysis: dict[str, Any]
    valuation_analysis: dict[str, Any]
    bull_case: dict[str, Any]
    bear_case: dict[str, Any]
    risk_analysis: dict[str, Any]
    portfolio_impact: dict[str, Any]

    # Evidence tracking & verification
    evidence: list[dict[str, Any]]
    contradictions: list[str]

    # Final recommendation & gates
    recommendation: dict[str, Any]
    confidence: float
    evidence_quality: str

    # Diagnostics & execution flow
    errors: list[str]
    warnings: list[str]
    execution_status: str
