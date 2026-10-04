from typing import Any

from pydantic import BaseModel, Field

from investment_agent.llm.providers import LLMProvider


class LLMModelConfig(BaseModel):
    provider: LLMProvider
    model_name: str
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    timeout_seconds: int = Field(default=60, gt=0)
    max_retries: int = Field(default=3, ge=0)
    api_key: str | None = None
    base_url: str | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)


class LLMRoutingConfig(BaseModel):
    primary: LLMModelConfig
    cheap: LLMModelConfig
    reasoning: LLMModelConfig
    local: LLMModelConfig
    fallback: LLMModelConfig | None = None
