from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from investment_agent.graph.edges import (
    after_candidate_screening_condition,
    after_recommendation_gate_condition,
)
from investment_agent.graph.nodes import (
    bear_case_node,
    bull_case_node,
    candidate_screening_node,
    evidence_verifier_node,
    fundamental_analysis_node,
    investment_report_node,
    load_portfolio_node,
    load_research_universe_node,
    load_user_profile_node,
    market_data_validation_node,
    news_analysis_node,
    portfolio_impact_node,
    recommendation_gate_node,
    recommendation_logger_node,
    risk_agent_node,
    valuation_analysis_node,
)
from investment_agent.graph.state import InvestmentGraphState


def create_investment_graph() -> CompiledStateGraph:
    """Build and compile the multi-node investment research and portfolio guidance graph."""
    builder = StateGraph(InvestmentGraphState)

    # Register Nodes
    builder.add_node("load_user_profile", load_user_profile_node)
    builder.add_node("load_portfolio", load_portfolio_node)
    builder.add_node("load_research_universe", load_research_universe_node)
    builder.add_node("market_data_validation", market_data_validation_node)
    builder.add_node("candidate_screening", candidate_screening_node)
    builder.add_node("fundamental_analysis", fundamental_analysis_node)
    builder.add_node("news_analysis", news_analysis_node)
    builder.add_node("valuation_analysis", valuation_analysis_node)
    builder.add_node("risk_agent", risk_agent_node)
    builder.add_node("bull_case", bull_case_node)
    builder.add_node("bear_case", bear_case_node)
    builder.add_node("portfolio_impact", portfolio_impact_node)
    builder.add_node("evidence_verifier", evidence_verifier_node)
    builder.add_node("recommendation_gate", recommendation_gate_node)
    builder.add_node("investment_report", investment_report_node)
    builder.add_node("recommendation_logger", recommendation_logger_node)

    # Connect Edges
    builder.add_edge(START, "load_user_profile")
    builder.add_edge("load_user_profile", "load_portfolio")
    builder.add_edge("load_portfolio", "load_research_universe")
    builder.add_edge("load_research_universe", "market_data_validation")
    builder.add_edge("market_data_validation", "candidate_screening")

    # Conditional branching after candidate screening
    builder.add_conditional_edges(
        "candidate_screening",
        after_candidate_screening_condition,
        {
            "continue_analysis": "fundamental_analysis",
            "no_candidates": "recommendation_gate",
        },
    )

    # Analysis Pipeline
    builder.add_edge("fundamental_analysis", "news_analysis")
    builder.add_edge("news_analysis", "valuation_analysis")
    builder.add_edge("valuation_analysis", "risk_agent")
    builder.add_edge("risk_agent", "bull_case")
    builder.add_edge("bull_case", "bear_case")
    builder.add_edge("bear_case", "portfolio_impact")
    builder.add_edge("portfolio_impact", "evidence_verifier")
    builder.add_edge("evidence_verifier", "recommendation_gate")

    # Conditional branching after recommendation gate
    builder.add_conditional_edges(
        "recommendation_gate",
        after_recommendation_gate_condition,
        {
            "opportunity": "investment_report",
            "no_action": "recommendation_logger",
        },
    )

    builder.add_edge("investment_report", "recommendation_logger")
    builder.add_edge("recommendation_logger", END)

    return builder.compile()
