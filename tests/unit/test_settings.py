from investment_agent.config.settings import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.APP_NAME == "AI Investment Research & Portfolio Guidance Agent"
    assert settings.LLM_PROVIDER in ["openai", "gemini", "anthropic", "groq", "ollama"]
    assert "postgresql+asyncpg://" in settings.async_database_url
    assert "postgresql://" in settings.sync_database_url
    assert "redis://" in settings.resolved_redis_url


def test_settings_custom_database_url():
    settings = Settings(DATABASE_URL="postgresql://myuser:mypass@dbhost:5432/mydb")
    assert settings.async_database_url == "postgresql+asyncpg://myuser:mypass@dbhost:5432/mydb"
    assert settings.sync_database_url == "postgresql://myuser:mypass@dbhost:5432/mydb"
