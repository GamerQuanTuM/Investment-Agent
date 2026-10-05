from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderType = Literal["openai", "gemini", "anthropic", "groq", "ollama"]
ModelTierType = Literal["primary", "cheap", "reasoning", "local", "fallback"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "AI Investment Research & Portfolio Guidance Agent"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Default LLM settings
    LLM_PROVIDER: LLMProviderType = "openai"
    LLM_MODEL: str = "gpt-4o"
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 3
    MAX_DAILY_LLM_COST_USD: float = 5.0

    # Model Routing: Tier-specific providers & models
    PRIMARY_LLM_PROVIDER: LLMProviderType = "openai"
    PRIMARY_LLM_MODEL: str = "gpt-4o"

    CHEAP_LLM_PROVIDER: LLMProviderType = "groq"
    CHEAP_LLM_MODEL: str = "llama-3.3-70b-versatile"

    REASONING_LLM_PROVIDER: LLMProviderType = "anthropic"
    REASONING_LLM_MODEL: str = "claude-3-7-sonnet-20250219"

    LOCAL_LLM_PROVIDER: LLMProviderType = "ollama"
    LOCAL_LLM_MODEL: str = "llama3.2"

    FALLBACK_LLM_PROVIDER: LLMProviderType = "gemini"
    FALLBACK_LLM_MODEL: str = "gemini-2.0-flash"

    # API Keys & URLs
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Database (PostgreSQL)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "investment_agent"
    DATABASE_URL: str | None = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql+asyncpg://"):
                return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str | None = None

    @property
    def resolved_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # Observability (LangSmith)
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "investment-agent"

    # HTTP
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # INDstocks (INDmoney broker) — prices, history, holdings. Read-only.
    INDSTOCKS_BASE_URL: str = "https://api.indstocks.com"
    INDSTOCKS_ACCESS_TOKEN: str | None = None
    INDSTOCKS_CLIENT_ID: str | None = None
    INDSTOCKS_MPIN: str | None = None
    INDSTOCKS_TOTP_SECRET: str | None = None
    INDSTOCKS_WATCHLIST: str = ""
    MARKET_DATA_MAX_AGE_HOURS: int = 36
    QUOTE_CACHE_TTL_SECONDS: int = 120
    # Stock-list picker liquidity floors: names below either are treated as penny/illiquid.
    STOCK_PICK_MIN_MARKET_CAP_CR: float = 5000.0
    STOCK_PICK_MIN_AVG_VOLUME: float = 100000.0

    # Mutual fund NAVs (official AMFI file, no API key)
    AMFI_NAV_URL: str = "https://portal.amfiindia.com/spages/NAVAll.txt"
    AMFI_SCHEME_CODES: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def indstocks_watchlist(self) -> list[str]:
        return [
            symbol.strip().upper()
            for symbol in self.INDSTOCKS_WATCHLIST.split(",")
            if symbol.strip()
        ]

    @property
    def amfi_scheme_codes(self) -> list[str]:
        return [code.strip() for code in self.AMFI_SCHEME_CODES.split(",") if code.strip()]

    @property
    def indstocks_configured(self) -> bool:
        if self.INDSTOCKS_ACCESS_TOKEN:
            return True
        return bool(self.INDSTOCKS_CLIENT_ID and self.INDSTOCKS_MPIN and self.INDSTOCKS_TOTP_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()
