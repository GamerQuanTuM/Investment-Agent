from enum import StrEnum


class LLMProvider(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    OLLAMA = "ollama"


class ModelTier(StrEnum):
    PRIMARY = "primary"
    CHEAP = "cheap"
    REASONING = "reasoning"
    LOCAL = "local"
    FALLBACK = "fallback"


SUPPORTED_PROVIDERS = {
    LLMProvider.OPENAI,
    LLMProvider.GEMINI,
    LLMProvider.ANTHROPIC,
    LLMProvider.GROQ,
    LLMProvider.OLLAMA,
}
