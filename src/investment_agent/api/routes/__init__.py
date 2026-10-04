from investment_agent.api.routes.health import router as health_router
from investment_agent.api.routes.market import router as market_router
from investment_agent.api.routes.research import router as research_router

__all__ = ["health_router", "market_router", "research_router"]
