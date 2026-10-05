"""Shared fixtures for the chat tests: a fixture security master, a controllable intent LLM,
and a fake Redis so no unit test ever opens a real connection."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from investment_agent.market import live_universe
from investment_agent.research import (
    chat,
    chat_ai,
    chat_intent,
    chat_session,
    education,
    stock_list_chat,
)

SYMBOL_MASTER: list[dict[str, str]] = [
    {"symbol": "TCS", "name": "Tata Consultancy Services Ltd"},
    {"symbol": "INFY", "name": "Infosys Limited"},
    {"symbol": "RELIANCE", "name": "Reliance Industries Limited"},
    {"symbol": "HDFCBANK", "name": "HDFC Bank Limited"},
    {"symbol": "TATAMOTORS", "name": "Tata Motors Limited"},
    # Real-looking tickers that are also everyday words must still never match "OK"/"YES"/"NO".
    {"symbol": "OK", "name": ""},
    {"symbol": "YES", "name": ""},
    {"symbol": "NO", "name": ""},
]


class FakeRedis:
    """Stands in for market/cache.py's cache_get/cache_set/cache_delete."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.down = False

    async def get(self, key: str) -> str | None:
        return None if self.down else self.store.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        if not self.down:
            self.store[key] = value
            self.ttls[key] = int(ttl)

    async def delete(self, key: str) -> None:
        if not self.down:
            self.store.pop(key, None)


class FakeLLM:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    redis = FakeRedis()
    monkeypatch.setattr(chat_session, "cache_get", redis.get)
    monkeypatch.setattr(chat_session, "cache_set", redis.set)
    monkeypatch.setattr(chat_session, "cache_delete", redis.delete)
    chat_session._memory.clear()
    yield redis
    chat_session._memory.clear()


@pytest.fixture(autouse=True)
def _chat_isolation(fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch):
    async def master() -> list[dict[str, str]]:
        return SYMBOL_MASTER

    monkeypatch.setattr(chat, "load_symbol_master", master)

    def no_llm(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("LLM disabled in unit tests")

    monkeypatch.setattr(chat_intent, "get_llm", no_llm)  # deterministic rules by default
    monkeypatch.setattr(education, "get_llm", no_llm)
    monkeypatch.setattr(chat_ai, "get_llm", no_llm)  # AI answers fall back to reviewed text
    monkeypatch.setattr(stock_list_chat, "get_llm", no_llm)


@pytest.fixture(autouse=True)
def _no_live_market_fetch(monkeypatch: pytest.MonkeyPatch):
    """The live universe fallback must never reach real providers from a unit test."""
    live_universe.reset_state()

    async def providers_down(wait_seconds: float | None = None) -> live_universe.LiveOutcome:
        return live_universe.LiveOutcome("failed", [])

    monkeypatch.setattr(live_universe, "get_candidates", providers_down)
    yield
    live_universe.reset_state()


@pytest.fixture
def use_llm(monkeypatch: pytest.MonkeyPatch):
    """`use_llm(json_text_or_exception)` installs a fake cheap-tier model for intent extraction."""

    def install(reply: str | Exception) -> FakeLLM:
        llm = FakeLLM(reply)
        monkeypatch.setattr(chat_intent, "get_llm", lambda *a, **k: llm)
        return llm

    return install


@pytest.fixture
def use_education_llm(monkeypatch: pytest.MonkeyPatch):
    def install(reply: str | Exception) -> FakeLLM:
        llm = FakeLLM(reply)
        monkeypatch.setattr(education, "get_llm", lambda *a, **k: llm)
        monkeypatch.setattr(chat_ai, "get_llm", lambda *a, **k: llm)
        return llm

    return install


@pytest.fixture
def use_summary_llm(monkeypatch: pytest.MonkeyPatch):
    def install(reply: str | Exception) -> FakeLLM:
        llm = FakeLLM(reply)
        monkeypatch.setattr(stock_list_chat, "get_llm", lambda *a, **k: llm)
        return llm

    return install


@pytest.fixture
def master() -> list[dict[str, str]]:
    return SYMBOL_MASTER
