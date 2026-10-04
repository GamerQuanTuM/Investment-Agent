# Multi-Model LLM Providers & Dynamic Routing

## 1. Provider Agnostic Architecture

The system never hardcodes a single LLM vendor. It supports:
1. **OpenAI** (e.g. `gpt-4o`, `o3-mini`) via `langchain-openai`
2. **Google Gemini** (e.g. `gemini-2.0-flash`, `gemini-1.5-pro`) via `langchain-google-genai`
3. **Anthropic** (e.g. `claude-3-7-sonnet-20250219`, `claude-3-5-haiku`) via `langchain-anthropic`
4. **Groq** (e.g. `llama-3.3-70b-versatile`) via `langchain-groq`
5. **Ollama** (e.g. `llama3.2`, `deepseek-r1`) via `langchain-ollama`

## 2. Model Routing Tiers

Rather than using one expensive model for every task, LangGraph nodes request specialized tiers:

```python
from investment_agent.llm.factory import get_llm

cheap_model = get_llm("cheap")          # Groq: high-speed data parsing & screening
reasoning_model = get_llm("reasoning")  # Anthropic: deep risk & dialectic bear analysis
primary_model = get_llm("primary")      # OpenAI: structured thesis & synthesis
local_model = get_llm("local")          # Ollama: offline / privacy-sensitive
```

## 3. Fallback Mechanism & Resilience

If the primary provider suffers an outage, rate limit, or timeout:
```python
base_model = create_chat_model(primary_config)
resilient_model = base_model.with_fallbacks([fallback_model])
```
This is transparent to the agent nodes.

## 4. Cost Control Policies

1. **Deterministic Pre-Filtering**: Deterministic candidate screening runs *before* invoking any LLM, filtering out over-leveraged companies, high promoter pledging, or illiquid assets.
2. **Daily Budget Cap**: Configured via `MAX_DAILY_LLM_COST_USD` in `.env`.
3. **Testing Overrides**: In unit tests, `register_tier_override(...)` enables injecting mock models without making external API calls.
