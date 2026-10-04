import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable

from investment_agent.config.settings import Settings, get_settings
from investment_agent.llm.config import LLMModelConfig, LLMRoutingConfig
from investment_agent.llm.providers import LLMProvider, ModelTier

logger = logging.getLogger(__name__)

# Test overrides registry
_TIER_OVERRIDES: dict[str, BaseChatModel | Runnable[Any, Any]] = {}


def register_tier_override(
    tier: str | ModelTier, model: BaseChatModel | Runnable[Any, Any]
) -> None:
    """Register an LLM instance override for a tier (useful for testing and offline mocks)."""
    tier_key = str(tier).lower()
    _TIER_OVERRIDES[tier_key] = model


def clear_tier_overrides() -> None:
    """Clear all registered tier overrides."""
    _TIER_OVERRIDES.clear()


def create_chat_model(config: LLMModelConfig) -> BaseChatModel:
    """Instantiate a LangChain chat model based on provider configuration."""
    provider = config.provider
    model_name = config.model_name
    temperature = config.temperature
    timeout = config.timeout_seconds
    max_retries = config.max_retries
    extra = config.extra_params or {}

    logger.debug(f"Creating chat model for provider '{provider}' and model '{model_name}'")

    if provider == LLMProvider.OPENAI:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": max_retries,
            **extra,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.max_tokens:
            kwargs["max_tokens"] = config.max_tokens
        return ChatOpenAI(**kwargs)

    elif provider == LLMProvider.GEMINI:
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {
            "model": model_name,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": max_retries,
            **extra,
        }
        if config.api_key:
            kwargs["google_api_key"] = config.api_key
        if config.max_tokens:
            kwargs["max_output_tokens"] = config.max_tokens
        return ChatGoogleGenerativeAI(**kwargs)

    elif provider == LLMProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        kwargs = {
            "model": model_name,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": max_retries,
            **extra,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.max_tokens:
            kwargs["max_tokens_to_sample"] = config.max_tokens
        return ChatAnthropic(**kwargs)

    elif provider == LLMProvider.GROQ:
        from langchain_groq import ChatGroq

        kwargs = {
            "model": model_name,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": max_retries,
            **extra,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.max_tokens:
            kwargs["max_tokens"] = config.max_tokens
        return ChatGroq(**kwargs)

    elif provider == LLMProvider.OLLAMA:
        from langchain_ollama import ChatOllama

        kwargs = {
            "model": model_name,
            "temperature": temperature,
            "base_url": config.base_url or "http://localhost:11434",
            **extra,
        }
        return ChatOllama(**kwargs)

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Supported providers: {[p.value for p in LLMProvider]}"
        )


def _resolve_api_key(provider: LLMProvider, cfg: Settings) -> str | None:
    if provider == LLMProvider.OPENAI:
        return cfg.OPENAI_API_KEY
    elif provider == LLMProvider.GEMINI:
        return cfg.GOOGLE_API_KEY
    elif provider == LLMProvider.ANTHROPIC:
        return cfg.ANTHROPIC_API_KEY
    elif provider == LLMProvider.GROQ:
        return cfg.GROQ_API_KEY
    return None


def build_routing_config(settings: Settings | None = None) -> LLMRoutingConfig:
    """Build routing config from application settings."""
    cfg = settings or get_settings()

    primary_provider = LLMProvider(cfg.PRIMARY_LLM_PROVIDER)
    primary_config = LLMModelConfig(
        provider=primary_provider,
        model_name=cfg.PRIMARY_LLM_MODEL,
        temperature=cfg.LLM_TEMPERATURE,
        timeout_seconds=cfg.LLM_TIMEOUT_SECONDS,
        max_retries=cfg.LLM_MAX_RETRIES,
        api_key=_resolve_api_key(primary_provider, cfg),
    )

    cheap_provider = LLMProvider(cfg.CHEAP_LLM_PROVIDER)
    cheap_config = LLMModelConfig(
        provider=cheap_provider,
        model_name=cfg.CHEAP_LLM_MODEL,
        temperature=cfg.LLM_TEMPERATURE,
        timeout_seconds=cfg.LLM_TIMEOUT_SECONDS,
        max_retries=cfg.LLM_MAX_RETRIES,
        api_key=_resolve_api_key(cheap_provider, cfg),
    )

    reasoning_provider = LLMProvider(cfg.REASONING_LLM_PROVIDER)
    reasoning_config = LLMModelConfig(
        provider=reasoning_provider,
        model_name=cfg.REASONING_LLM_MODEL,
        temperature=cfg.LLM_TEMPERATURE,
        timeout_seconds=cfg.LLM_TIMEOUT_SECONDS,
        max_retries=cfg.LLM_MAX_RETRIES,
        api_key=_resolve_api_key(reasoning_provider, cfg),
    )

    local_provider = LLMProvider(cfg.LOCAL_LLM_PROVIDER)
    local_config = LLMModelConfig(
        provider=local_provider,
        model_name=cfg.LOCAL_LLM_MODEL,
        temperature=cfg.LLM_TEMPERATURE,
        base_url=cfg.OLLAMA_BASE_URL,
        api_key=_resolve_api_key(local_provider, cfg),
    )

    fallback_config = None
    if cfg.FALLBACK_LLM_PROVIDER:
        fallback_provider = LLMProvider(cfg.FALLBACK_LLM_PROVIDER)
        fallback_config = LLMModelConfig(
            provider=fallback_provider,
            model_name=cfg.FALLBACK_LLM_MODEL,
            temperature=cfg.LLM_TEMPERATURE,
            timeout_seconds=cfg.LLM_TIMEOUT_SECONDS,
            max_retries=cfg.LLM_MAX_RETRIES,
            api_key=_resolve_api_key(fallback_provider, cfg),
        )

    return LLMRoutingConfig(
        primary=primary_config,
        cheap=cheap_config,
        reasoning=reasoning_config,
        local=local_config,
        fallback=fallback_config,
    )


def get_llm(
    tier: str | ModelTier = ModelTier.PRIMARY,
    enable_fallback: bool = True,
    settings: Settings | None = None,
) -> BaseChatModel | Runnable[Any, Any]:
    """Retrieve an instantiated LangChain chat model for a requested model tier.

    Supports:
        - "primary": High-capability model for final synthesis & structured thesis
        - "cheap": Fast/inexpensive model for screening, extraction, and filtering
        - "reasoning": Deep analytical model for bull/bear tension and risk checks
        - "local": Offline Ollama model for privacy or fallback
        - "fallback": Standby secondary model
    """
    tier_str = str(tier).lower()
    if tier_str in _TIER_OVERRIDES:
        logger.info(f"Using registered override LLM for tier '{tier_str}'")
        return _TIER_OVERRIDES[tier_str]

    routing = build_routing_config(settings)

    tier_map: dict[str, LLMModelConfig] = {
        ModelTier.PRIMARY.value: routing.primary,
        ModelTier.CHEAP.value: routing.cheap,
        ModelTier.REASONING.value: routing.reasoning,
        ModelTier.LOCAL.value: routing.local,
    }
    if routing.fallback:
        tier_map[ModelTier.FALLBACK.value] = routing.fallback

    if tier_str not in tier_map:
        raise ValueError(f"Unknown model tier: '{tier}'. Supported tiers: {list(tier_map.keys())}")

    model_config = tier_map[tier_str]
    base_model = create_chat_model(model_config)

    # Attach fallback model if requested and tier is not already fallback
    if enable_fallback and routing.fallback and tier_str != ModelTier.FALLBACK.value:
        try:
            fallback_model = create_chat_model(routing.fallback)
            return base_model.with_fallbacks([fallback_model])
        except Exception as e:
            logger.warning(f"Could not initialize fallback model: {e}")
            return base_model

    return base_model
