from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from investment_agent.config.settings import Settings
from investment_agent.llm.factory import clear_tier_overrides
from investment_agent.main import create_app


@pytest.fixture(autouse=True)
def clean_llm_overrides():
    """Ensure clean LLM tier overrides before and after each test."""
    clear_tier_overrides()
    yield
    clear_tier_overrides()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        APP_ENV="test",
        DEBUG=True,
        OPENAI_API_KEY="test-openai-key",
        GOOGLE_API_KEY="test-google-key",
        ANTHROPIC_API_KEY="test-anthropic-key",
        GROQ_API_KEY="test-groq-key",
    )


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
