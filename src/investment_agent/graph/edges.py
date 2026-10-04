from typing import Literal

from investment_agent.graph.state import InvestmentGraphState


def after_candidate_screening_condition(
    state: InvestmentGraphState,
) -> Literal["continue_analysis", "no_candidates"]:
    """Conditional edge after candidate screening.

    If no candidates passed deterministic screening, bypass expensive LLM
    analyses and jump straight to the recommendation gate.
    """
    candidates = state.get("candidates", [])
    if not candidates:
        return "no_candidates"
    return "continue_analysis"


def after_recommendation_gate_condition(
    state: InvestmentGraphState,
) -> Literal["opportunity", "no_action"]:
    """Conditional edge after recommendation gate: Opportunity vs NO ACTION."""
    rec = state.get("recommendation", {})
    decision = rec.get("decision", "NO_ACTION")
    if decision == "OPPORTUNITY":
        return "opportunity"
    return "no_action"
