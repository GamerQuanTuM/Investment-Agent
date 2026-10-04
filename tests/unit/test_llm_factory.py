import pytest
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from investment_agent.config.settings import Settings
from investment_agent.llm.config import LLMModelConfig
from investment_agent.llm.factory import (
    build_routing_config,
    create_chat_model,
    get_llm,
    register_tier_override,
)
from investment_agent.llm.providers import LLMProvider


def test_create_openai_model():
    cfg = LLMModelConfig(
        provider=LLMProvider.OPENAI,
        model_name="gpt-4o",
        temperature=0.2,
        api_key="sk-test-key",
    )
    model = create_chat_model(cfg)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o"
    assert model.temperature == 0.2


def test_create_gemini_model():
    cfg = LLMModelConfig(
        provider=LLMProvider.GEMINI,
        model_name="gemini-2.0-flash",
        temperature=0.1,
        api_key="test-gemini-key",
    )
    model = create_chat_model(cfg)
    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model == "gemini-2.0-flash"
    assert model.temperature == 0.1


def test_create_anthropic_model():
    cfg = LLMModelConfig(
        provider=LLMProvider.ANTHROPIC,
        model_name="claude-3-5-sonnet-20241022",
        temperature=0.3,
        api_key="sk-ant-test",
    )
    model = create_chat_model(cfg)
    assert isinstance(model, ChatAnthropic)
    assert model.model == "claude-3-5-sonnet-20241022"


def test_create_groq_model():
    cfg = LLMModelConfig(
        provider=LLMProvider.GROQ,
        model_name="llama-3.3-70b-versatile",
        temperature=0.1,
        api_key="gsk_test",
    )
    model = create_chat_model(cfg)
    assert isinstance(model, ChatGroq)
    assert model.model_name == "llama-3.3-70b-versatile"


def test_create_ollama_model():
    cfg = LLMModelConfig(
        provider=LLMProvider.OLLAMA,
        model_name="llama3.2",
        temperature=0.0,
        base_url="http://localhost:11434",
    )
    model = create_chat_model(cfg)
    assert isinstance(model, ChatOllama)
    assert model.model == "llama3.2"


def test_unsupported_provider():
    with pytest.raises(ValueError):
        create_chat_model(
            LLMModelConfig(
                provider="unsupported_provider",  # type: ignore
                model_name="test",
            )
        )


def test_build_routing_config():
    settings = Settings(
        PRIMARY_LLM_PROVIDER="openai",
        PRIMARY_LLM_MODEL="gpt-4o",
        CHEAP_LLM_PROVIDER="groq",
        CHEAP_LLM_MODEL="llama-3.3-70b-versatile",
        REASONING_LLM_PROVIDER="anthropic",
        REASONING_LLM_MODEL="claude-3-7-sonnet-20250219",
        LOCAL_LLM_PROVIDER="ollama",
        LOCAL_LLM_MODEL="llama3.2",
    )
    routing = build_routing_config(settings)
    assert routing.primary.provider == LLMProvider.OPENAI
    assert routing.cheap.provider == LLMProvider.GROQ
    assert routing.reasoning.provider == LLMProvider.ANTHROPIC
    assert routing.local.provider == LLMProvider.OLLAMA


def test_tier_override():
    # Create a dummy model
    dummy = ChatOllama(model="llama3.2")
    register_tier_override("primary", dummy)

    selected = get_llm("primary")
    assert selected is dummy
