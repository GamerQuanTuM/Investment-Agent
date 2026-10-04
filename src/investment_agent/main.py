import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from investment_agent.api.routes import health_router, market_router, research_router
from investment_agent.config.settings import get_settings

logger = logging.getLogger("investment_agent")
settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting {settings.APP_NAME} in '{settings.APP_ENV}' mode")
    logger.info(
        f"Active LLM Routing Configuration -> "
        f"Primary: {settings.PRIMARY_LLM_PROVIDER}:{settings.PRIMARY_LLM_MODEL} | "
        f"Cheap: {settings.CHEAP_LLM_PROVIDER}:{settings.CHEAP_LLM_MODEL} | "
        f"Reasoning: {settings.REASONING_LLM_PROVIDER}:{settings.REASONING_LLM_MODEL} | "
        f"Local: {settings.LOCAL_LLM_PROVIDER}:{settings.LOCAL_LLM_MODEL}"
    )
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "AI Investment Research & Portfolio Guidance Agent for the Indian market. "
            "Evidence-based research, deterministic screening, and multi-model LLM routing."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(market_router)
    app.include_router(research_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("investment_agent.main:app", host=settings.HOST, port=settings.PORT, reload=True)
