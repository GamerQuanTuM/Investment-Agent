"""Chat memory: context formatting, prompt wiring, and Tavily-first news."""

from __future__ import annotations

import json

import httpx
import respx

from investment_agent.market import news, tavily
from investment_agent.research import chat_ai, chat_memory


def test_format_context_puts_related_older_messages_before_latest_and_dedupes():
    recent = [{"role": "user", "text": "what is a SIP"}, {"role": "assistant", "text": "A SIP is..."}]
    recalled = [
        {"role": "user", "text": "I have 5 years to invest"},
        {"role": "user", "text": "what is a SIP"},  # already in the latest turns
    ]
    text = chat_memory.format_context(recent, recalled)
    assert text.index("5 years") < text.index("Latest messages")
    assert text.count("what is a SIP") == 1


async def test_ai_prompt_includes_conversation_context(use_education_llm):
    llm = use_education_llm("- **ETFs** trade like shares.")
    token = chat_memory.conversation_context.set("Latest messages:\n- user: tell me about ETFs")
    try:
        await chat_ai.write("explain", "and how do I buy it?")
    finally:
        chat_memory.conversation_context.reset(token)
    assert "tell me about ETFs" in llm.prompts[0]


async def test_memory_disabled_without_google_key(monkeypatch):
    monkeypatch.setattr(chat_memory, "_enabled", lambda: False)
    assert await chat_memory.recall("s1", "anything") == []
    await chat_memory.remember("s1", "user", "hello")  # must not raise


@respx.mock
async def test_news_prefers_tavily_and_falls_back_to_rss(monkeypatch):
    async def no_cache(*a, **k):
        return None

    monkeypatch.setattr(news, "cache_get", no_cache)
    monkeypatch.setattr(news, "cache_set", no_cache)
    monkeypatch.setattr(tavily, "get_settings", lambda: type("S", (), {"TAVILY_API_KEY": "k"})())
    respx.post(tavily.TAVILY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "TCS wins deal", "url": "https://example.com/a", "score": 0.9}]},
        )
    )
    articles = await news.get_news("TCS")
    assert articles[0]["title"] == "TCS wins deal"
    assert articles[0]["source_name"] == "example.com"
    assert json.loads(respx.calls[0].request.content)["topic"] == "news"


# ---- research consultant -------------------------------------------------------------

ROWS = [{"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT", "score": 71.5,
         "why": ["steady profitability"], "signals": {}, "market_cap_band": "large"}]


def _news_tools(monkeypatch, items):
    from investment_agent.research import consultant

    async def fake_tavily(query, **kw):
        return items

    async def none(*a, **k):
        return None

    async def macro():
        return {"usd_inr": {"status": "OK", "rate": 83.1}}

    monkeypatch.setattr(consultant, "tavily_search", fake_tavily)
    monkeypatch.setattr(consultant, "cache_get", none)
    monkeypatch.setattr(consultant, "cache_set", none)
    monkeypatch.setattr(consultant, "get_macro_snapshot", macro)
    return consultant


async def test_consultant_brief_keeps_grounded_text_and_drops_advice(monkeypatch, use_education_llm):
    consultant = _news_tools(monkeypatch, [{"title": "TCS wins large deal", "url": "https://x.com/a", "content": "Deal win."}])
    reply = {
        "market": "Markets were mixed.",
        "stocks": {"TCS": {
            "why_picked": "It has steady profitability.",
            "in_favour": ["You should buy it now.", "A large, established company."],
            "watch_out": ["Tech spending can slow.", "Invented 99 percent growth."],
            "recent": [{"text": "TCS won a large deal.", "url": "https://x.com/a"},
                       {"text": "Made-up story.", "url": "https://evil.example/zzz"}],
            "check_before_deciding": ["Read the latest results."],
        }},
    }
    monkeypatch.setattr(consultant, "get_llm", lambda *a, **k: use_education_llm(json.dumps(reply)))
    research = await consultant.research_stocks(ROWS)
    brief = research["briefs"]["TCS"]
    assert brief["in_favour"] == ["A large, established company."]  # advice sentence dropped
    assert brief["watch_out"] == ["Tech spending can slow."]  # ungrounded number dropped
    assert brief["recent"][1]["url"] is None  # link not from a tool is removed
    assert "tavily" in research["tools_used"]
    text = consultant.render(ROWS, research)
    assert "The decision is yours" in text and "https://x.com/a" in text


async def test_consultant_falls_back_when_model_down(monkeypatch):
    consultant = _news_tools(monkeypatch, [])
    research = await consultant.research_stocks(ROWS)
    assert research["status"] == "OK"
    brief = research["briefs"]["TCS"]
    assert brief["written_by"] == "reviewed" and brief["watch_out"]


async def test_consultant_never_exceeds_its_time_budget(monkeypatch):
    import asyncio
    import time

    consultant = _news_tools(monkeypatch, [])
    monkeypatch.setattr(consultant, "TOTAL_BUDGET_SECONDS", 9.0)
    monkeypatch.setattr(consultant, "MIN_SYNTHESIS_SECONDS", 0.5)

    class Slow:
        async def ainvoke(self, prompt):
            await asyncio.sleep(60)

    monkeypatch.setattr(consultant, "get_llm", lambda *a, **k: Slow())
    start = time.monotonic()
    research = await consultant.research_stocks(ROWS)
    assert time.monotonic() - start < 12
    assert research["briefs"]["TCS"]["written_by"] == "reviewed"


# ---- research mode, scope and streaming ----------------------------------------------

async def test_research_mode_answers_with_cited_sources_and_drops_advice(monkeypatch, use_education_llm):
    consultant = _news_tools(
        monkeypatch,
        [{"title": "SEBI revises margin rules", "url": "https://www.sebi.gov.in/a", "content": "Margin rules changed."}],
    )
    real = consultant.get_settings()
    monkeypatch.setattr(consultant, "get_settings", lambda: real.model_copy(update={"TAVILY_API_KEY": "k"}))
    reply = {
        "in_scope": True,
        "answer": "SEBI changed margin rules [1].\n- You should buy brokers now [1].\n- Brokers must collect margins upfront [1].",
    }
    monkeypatch.setattr(consultant, "get_llm", lambda *a, **k: use_education_llm(json.dumps(reply)))
    result = await consultant.research_answer("what did SEBI change in margin rules")
    assert result["status"] == "OK"
    assert "buy brokers" not in result["text"]
    assert "[1](https://www.sebi.gov.in/a)" in result["text"]


async def test_research_mode_declines_off_topic_and_reports_missing_key(monkeypatch):
    from investment_agent.research import chat, consultant

    monkeypatch.setattr(consultant, "get_settings", lambda: type("S", (), {"TAVILY_API_KEY": None})())
    out = await chat.chat_turn("s-r1", "what is the capital of France", research=True)
    assert out["intent"] == "off_topic" or "only answer questions about stocks" in out["text"]
    out = await chat.chat_turn("s-r2", "what is an ETF", research=True)
    assert "TAVILY_API_KEY" in out["text"]  # unit tests run without a key


async def test_progress_events_reach_the_sink():
    from investment_agent.research import progress

    seen = []
    progress.set_sink(seen.append)
    progress.emit("search", "Searching", "x")
    progress.emit("search", "Searched", done=True)
    progress.set_sink(None)
    assert [e["status"] for e in seen] == ["running", "done"]


async def test_event_stream_relays_steps_then_reply_or_error():
    import json as _json

    from investment_agent.api.routes.research import _event_stream
    from investment_agent.research import progress

    async def ok():
        progress.emit("search", "Searching the web", "TCS")
        return {"text": "done"}

    frames = [f async for f in _event_stream(ok)]
    events = [_json.loads(f[6:]) for f in frames if f.startswith("data: ")]
    assert [e["type"] for e in events] == ["step", "reply"]
    assert events[0]["label"] == "Searching the web" and events[1]["data"] == {"text": "done"}

    async def boom():
        raise RuntimeError("provider down")

    events = [_json.loads(f[6:]) async for f in _event_stream(boom) if f.startswith("data: ")]
    assert events[-1] == {"type": "error", "message": "provider down"}
