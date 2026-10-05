"""Bug 1: "Suggest 10 stocks for ₹10,000" with an empty database. The picker falls back to a
live universe (Yahoo/TradingView helpers mocked here), reports loading/failure honestly, and
the background sync never raises."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from investment_agent.config.settings import get_settings
from investment_agent.market import auto_sync, live_universe, yahoo_market
from investment_agent.research import chat, stock_list_chat

REAL_GET_CANDIDATES = live_universe.get_candidates  # the conftest stub replaces it per test

SECTORS = ["Technology", "Financial Services", "Healthcare", "Energy", "Consumer Defensive", "Industrials"]
SYMBOLS = [f"LIVE{i:02d}" for i in range(24)]
MESSAGE = "Suggest 10 stocks for ₹10,000"


def _index(symbol: str) -> int:
    return int(symbol[4:])


class FakeProviders:
    def __init__(self) -> None:
        self.calls = 0
        self.down = False
        self.delay = 0.0

    async def _gate(self) -> None:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.down:
            raise RuntimeError("provider down")

    async def quote_symbol(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        await self._gate()
        return {"symbol": symbol, "name": f"{symbol} Limited", "live_price": 300.0, "market_cap_cr": 90_000.0}

    async def chart_symbol(self, symbol: str, range_key: str, exchange: str = "NSE") -> dict[str, Any]:
        await self._gate()
        start = datetime.now(UTC) - timedelta(days=260)
        base = 300.0 + _index(symbol) * 11
        candles = [
            {
                "ts": int((start + timedelta(days=d)).timestamp()),
                "close": base + (d % 9) * 0.8 + d * 0.05,
                "volume": 1_500_000,
            }
            for d in range(260)
        ]
        return {"symbol": symbol, "candles": candles}

    async def company_fundamentals(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        await self._gate()
        i = _index(symbol)
        return {
            "sector": SECTORS[i % len(SECTORS)],
            "roe_pct": 12.0 + (i % 7) * 2,
            "debt_to_equity": 0.4,
            "eps": 15.0,
            "book_value": 120.0,
            "source": "Yahoo Finance company profile",
        }

    async def financial_statement_history(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        await self._gate()
        return {  # most recent first, like Yahoo
            "income_statements": [
                {"end_date": f"{2025 - n}-03-31", "total_revenue": 1000.0 * 1.1 ** (3 - n),
                 "net_income": 100.0 * 1.12 ** (3 - n), "ebit": 160.0, "interest_expense": 10.0}
                for n in range(4)
            ],
            "balance_sheets": [{"end_date": "2025-03-31", "total_assets": 1200.0, "total_current_liabilities": 200.0}],
            "cash_flows": [{"end_date": "2025-03-31", "operating_cash_flow": 150.0, "capex": -40.0}],
        }


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> FakeProviders:
    fake = FakeProviders()
    for name in ("quote_symbol", "chart_symbol", "company_fundamentals", "financial_statement_history"):
        monkeypatch.setattr(yahoo_market, name, getattr(fake, name))
    store: dict[str, str] = {}

    async def cache_get(key: str) -> str | None:
        return store.get(key)

    async def cache_set(key: str, value: str, ttl: int) -> None:
        store[key] = value

    persisted: list[int] = []

    async def persist(snapshots: dict[str, Any], series: dict[str, Any]) -> None:
        persisted.append(len(snapshots))

    async def no_tradingview(symbol: str, fundamentals: dict[str, Any], timeout: float) -> dict[str, Any]:
        return fundamentals

    monkeypatch.setattr(live_universe, "cache_get", cache_get)
    monkeypatch.setattr(live_universe, "cache_set", cache_set)
    monkeypatch.setattr(live_universe, "persist", persist)
    monkeypatch.setattr(live_universe, "_fill_gaps_from_tradingview", no_tradingview)
    monkeypatch.setattr(live_universe, "candidate_symbols", lambda: list(SYMBOLS))
    monkeypatch.setattr(live_universe, "RETRY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(live_universe, "get_candidates", REAL_GET_CANDIDATES)
    fake.persisted = persisted  # type: ignore[attr-defined]
    fake.cache = store  # type: ignore[attr-defined]

    async def empty_db(**kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(stock_list_chat, "load_pick_universe", empty_db)
    return fake


def _sid() -> str:
    return f"live-{uuid.uuid4().hex[:8]}"


async def test_empty_db_with_live_providers_returns_a_valid_plan(providers):
    result = await chat.chat_turn(_sid(), MESSAGE)
    plan = result["stock_plan"]
    assert result["intent"] == "stock_list", result["text"]
    assert plan is not None, (result["text"], result.get("data_reason"))
    rows = plan["rows"]
    assert 3 <= len(rows) <= 10
    assert {r["symbol"] for r in rows} <= set(SYMBOLS)  # tickers only from the real universe
    assert all(isinstance(r["shares"], int) and r["shares"] >= 1 for r in rows)
    assert plan["total_invested"] == pytest.approx(sum(r["shares"] * r["price"] for r in rows), abs=0.05)
    assert plan["total_invested"] <= 10_000
    assert plan["leftover"] == pytest.approx(10_000 - plan["total_invested"], abs=0.01)
    per_sector: dict[str, int] = {}
    for r in rows:
        per_sector[r["sector"]] = per_sector.get(r["sector"], 0) + 1
    assert max(per_sector.values()) <= 2
    names = {s["source_name"] for s in result["sources"]}
    assert "Yahoo Finance price history" in names
    assert "DATA_UNAVAILABLE" not in result["text"] and "/market" not in result["text"]
    assert providers.persisted == [len(SYMBOLS)]  # stored for the next request


async def test_second_request_reuses_the_live_result(providers):
    await chat.chat_turn(_sid(), MESSAGE)
    calls = providers.calls
    again = await chat.chat_turn(_sid(), MESSAGE)
    assert again["stock_plan"] is not None
    assert providers.calls == calls


async def test_providers_down_gives_the_friendly_error_and_no_endpoint_names(providers):
    providers.down = True
    result = await chat.chat_turn(_sid(), MESSAGE)
    assert result["stock_plan"] is None
    assert result["data_status"] == "DATA_UNAVAILABLE"
    assert "couldn't reach the market data providers" in result["text"].lower()
    assert "try again in a few minutes" in result["text"].lower()
    for banned in ("/market", "POST", "refresh", "DATA_UNAVAILABLE"):
        assert banned not in result["text"]


async def test_slow_fetch_says_loading_then_try_again_builds_the_plan(
    providers, monkeypatch: pytest.MonkeyPatch
):
    providers.delay = 0.15
    monkeypatch.setattr(get_settings(), "LIVE_UNIVERSE_WAIT_SECONDS", 0.02)
    session_id = _sid()
    loading = await chat.chat_turn(session_id, MESSAGE)
    assert loading["stock_plan"] is None
    assert "loading fresh market data" in loading["text"].lower()
    assert "about a minute" in loading["text"].lower()
    assert "Try again" in loading["suggestions"]
    assert "DATA_UNAVAILABLE" not in loading["text"] and "/market" not in loading["text"]
    assert loading["data_status"] == "LOADING"

    await live_universe._state.task  # the single shared fetch finishes
    done = await chat.chat_turn(session_id, "Try again")
    assert done["intent"] == "stock_list"
    assert done["stock_plan"] is not None
    assert done["collected"]["amount_inr"] == 10000.0


async def test_only_one_fetch_runs_for_concurrent_requests(providers, monkeypatch: pytest.MonkeyPatch):
    providers.delay = 0.05
    monkeypatch.setattr(get_settings(), "LIVE_UNIVERSE_WAIT_SECONDS", 5.0)
    first, second = await asyncio.gather(chat.chat_turn(_sid(), MESSAGE), chat.chat_turn(_sid(), MESSAGE))
    assert first["stock_plan"] and second["stock_plan"]
    assert providers.calls == len(SYMBOLS) * 4  # quote, chart, fundamentals, statements: once each


async def test_symbols_without_data_are_left_out_never_invented(providers, monkeypatch: pytest.MonkeyPatch):
    original = providers.quote_symbol

    async def quote(symbol: str, exchange: str = "NSE") -> dict[str, Any] | None:
        return None if _index(symbol) % 2 else await original(symbol, exchange)

    monkeypatch.setattr(yahoo_market, "quote_symbol", quote)
    snapshots, series = await live_universe.fetch_snapshots()
    assert set(snapshots) == {s for s in SYMBOLS if _index(s) % 2 == 0}
    assert set(series) == set(snapshots)


# ---------------------------------------------------------------------- background sync


async def test_startup_sync_does_not_raise_when_providers_fail(providers, monkeypatch: pytest.MonkeyPatch):
    from investment_agent.market import sync

    providers.down = True

    async def broken_refresh(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("database down")

    async def broken_schemes(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("AMFI down")

    monkeypatch.setattr(sync, "refresh_market_data", broken_refresh)
    monkeypatch.setattr(sync, "sync_mutual_fund_schemes", broken_schemes)
    auto_sync.state.in_progress = False
    await auto_sync.run_sync_once()
    assert auto_sync.state.in_progress is False
    assert auto_sync.state.last_error
    assert auto_sync.state.last_sync_at is None or auto_sync.state.last_error


async def test_sync_loop_survives_a_failing_check(monkeypatch: pytest.MonkeyPatch):
    async def boom() -> bool:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(auto_sync, "needs_initial_sync", boom)
    await auto_sync.sync_loop()  # logs and returns; must not raise


async def test_sync_loop_syncs_immediately_when_the_database_is_empty(monkeypatch: pytest.MonkeyPatch):
    ran = asyncio.Event()

    async def empty() -> bool:
        return True

    async def fake_run() -> None:
        ran.set()
        raise asyncio.CancelledError  # stop the loop after the first sync

    monkeypatch.setattr(auto_sync, "needs_initial_sync", empty)
    monkeypatch.setattr(auto_sync, "run_sync_once", fake_run)
    with pytest.raises(asyncio.CancelledError):
        await auto_sync.sync_loop()
    assert ran.is_set()


def test_background_sync_is_off_in_test_env_and_when_disabled(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "APP_ENV", "test")
    assert auto_sync.start_background_sync() is None
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "MARKET_AUTO_SYNC_ENABLED", False)
    assert auto_sync.start_background_sync() is None


def test_sync_schedule_is_market_hours_aware():
    interval = timedelta(hours=6)
    ist = auto_sync.IST
    monday_noon = datetime(2026, 10, 5, 12, 0, tzinfo=ist)  # market open
    assert auto_sync.is_market_open(monday_noon)
    assert auto_sync.should_sync(monday_noon, None, interval)
    assert not auto_sync.should_sync(monday_noon, monday_noon - timedelta(hours=2), interval)
    assert auto_sync.should_sync(monday_noon, monday_noon - timedelta(hours=7), interval)
    evening = datetime(2026, 10, 5, 20, 0, tzinfo=ist)  # closed; synced before the close
    assert auto_sync.should_sync(evening, datetime(2026, 10, 5, 14, 0, tzinfo=ist), interval)
    assert not auto_sync.should_sync(evening, datetime(2026, 10, 5, 16, 0, tzinfo=ist), interval)
    saturday = datetime(2026, 10, 10, 11, 0, tzinfo=ist)  # weekend: only the Friday close matters
    assert not auto_sync.is_market_open(saturday)
    assert not auto_sync.should_sync(saturday, datetime(2026, 10, 9, 16, 0, tzinfo=ist), interval)
    assert auto_sync.should_sync(saturday, datetime(2026, 10, 9, 10, 0, tzinfo=ist), interval)


async def test_market_status_reports_sync_fields(monkeypatch: pytest.MonkeyPatch):
    from investment_agent.api.routes.market import market_status

    async def counts() -> dict[str, int | None]:
        return {"fundamental_snapshots": 0, "daily_bars": 0, "mutual_fund_schemes": 0, "nav_records": 0}

    monkeypatch.setattr(auto_sync, "table_counts", counts)
    auto_sync.state.last_sync_at = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
    auto_sync.state.in_progress = True
    try:
        status = await market_status()
    finally:
        auto_sync.state.in_progress = False
        auto_sync.state.last_sync_at = None
    assert status["last_sync_at"] == "2026-10-05T09:00:00+00:00"
    assert status["sync_in_progress"] is True
    assert set(status["rows"]) == {"fundamental_snapshots", "daily_bars", "mutual_fund_schemes", "nav_records"}
    assert "watchlist" in status  # existing fields are untouched


@pytest.mark.parametrize("llm", ["rules", "mocked"])
async def test_bug_report_conversation_with_model_mocked_and_unavailable(providers, use_llm, llm):
    if llm == "mocked":
        use_llm(json.dumps({"intent": "stock_list", "slots": {"amount_inr": 10000, "stock_count": 10}}))
    result = await chat.chat_turn(_sid(), MESSAGE)
    assert result["intent"] == "stock_list"
    assert result["stock_plan"] is not None
    assert "isn't loaded" not in result["text"] and "/market" not in result["text"]
