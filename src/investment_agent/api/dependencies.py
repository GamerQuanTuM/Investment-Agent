from langgraph.graph.state import CompiledStateGraph

from investment_agent.config.settings import Settings, get_settings
from investment_agent.graph.workflow import create_investment_graph

# Global compiled graph singleton for API request reuse
_GRAPH_INSTANCE: CompiledStateGraph | None = None


def get_investment_graph() -> CompiledStateGraph:
    global _GRAPH_INSTANCE
    if _GRAPH_INSTANCE is None:
        _GRAPH_INSTANCE = create_investment_graph()
    return _GRAPH_INSTANCE


def get_app_settings() -> Settings:
    return get_settings()
