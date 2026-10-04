"""Tests for market/news.py. The fixture XML mirrors Google News RSS's real item shape
(confirmed live-reachable from this environment, see news.py's docstring) but uses
hand-written headlines so sentiment scoring in test_sentiment.py has deterministic,
documented expectations rather than depending on whatever is in the news on a given day.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from investment_agent.market import news

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get(key: str) -> str | None:
        return None

    async def _fake_set(key: str, value: str, ttl_seconds: object) -> None:
        return None

    monkeypatch.setattr(news, "cache_get", _fake_get)
    monkeypatch.setattr(news, "cache_set", _fake_set)


@respx.mock
async def test_get_news_parses_fixture_items():
    xml_body = (FIXTURES_DIR / "google_news_tcs.xml").read_text(encoding="utf-8")
    respx.get(news.GOOGLE_NEWS_RSS_URL).mock(return_value=httpx.Response(200, text=xml_body))

    articles = await news.get_news("TCS stock NSE")

    assert len(articles) == 3
    assert articles[0]["title"] == "TCS shares surge after wins contract from global bank - zeebiz.com"
    assert articles[0]["source_name"] == "zeebiz.com"
    assert articles[0]["link"] == "https://news.google.com/rss/articles/AAA?oc=5"
    assert articles[0]["published_at"] == "2026-10-03T18:28:21+00:00"


@respx.mock
async def test_get_news_empty_query_short_circuits_without_a_request():
    # No respx route registered -- if this made a request, respx would raise.
    assert await news.get_news("   ") == []


@respx.mock
async def test_get_news_degrades_to_empty_list_on_server_error():
    respx.get(news.GOOGLE_NEWS_RSS_URL).mock(return_value=httpx.Response(500))
    assert await news.get_news("TCS") == []


@respx.mock
async def test_get_news_degrades_to_empty_list_on_unparseable_xml():
    respx.get(news.GOOGLE_NEWS_RSS_URL).mock(return_value=httpx.Response(200, text="not xml at all"))
    assert await news.get_news("TCS") == []
