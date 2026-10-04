"""Shared fixtures for market provider tests.

The pattern every new provider test should follow:
1. Record a representative (trimmed, non-sensitive) JSON response from the real API once,
   save it under tests/unit/market/fixtures/<provider>_<case>.json.
2. Use `respx` to mock the httpx call(s) and return that fixture body.
3. Assert on the parsed/normalized output, not on the raw fixture, so the test still catches
   regressions in the provider's own parsing logic.

See test_yahoo_market.py for a worked example (quote_symbol, including the crumb/cookie
handshake and the cache-wiring from Gap 6).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    """Fixture factory: call `load_fixture("name.json")` to read a recorded response body.

    Exposed as a fixture (not a plain importable function) because this file has no package
    `__init__.py`, so other test modules in this directory cannot `import` from it directly —
    pytest's own conftest fixture-discovery is the supported way to share this across tests.
    """

    def _load(name: str) -> Any:
        with (FIXTURES_DIR / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    return _load


@pytest.fixture
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make cache_get/cache_set no-ops so provider tests never touch a real Redis instance.

    `cache_get`/`cache_set` are imported with `from ... import` into each provider module
    (e.g. yahoo_market.py), which binds a separate name in that module's namespace — patching
    investment_agent.market.cache itself would not affect those call sites. Patch every module
    that currently imports them here as new providers adopt the Gap 6 cache.
    """
    import investment_agent.market.yahoo_market as yahoo_module

    async def _fake_get(key: str) -> str | None:
        return None

    async def _fake_set(key: str, value: str, ttl_seconds: object) -> None:
        return None

    for module in (yahoo_module,):
        monkeypatch.setattr(module, "cache_get", _fake_get)
        monkeypatch.setattr(module, "cache_set", _fake_set)
