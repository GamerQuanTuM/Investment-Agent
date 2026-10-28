"""AI research consultant: gathers evidence with every tool, then writes a brief the user decides on.

For each stock in a plan the code runs the research tools in parallel:

- Tavily web search (recent company news, with snippets and links)
- Google News RSS headlines (fallback when Tavily is off or empty) scored by the sentiment lexicon
- the picker's own factor scores (quality, valuation, momentum, risk) and signals
- the macro snapshot (USD/INR, CPI) and one Tavily search on the overall Indian market

A model then turns that evidence into a short brief per stock: why it was picked, what is in
its favour, what to watch, what was in the news (with links), and what to check before
deciding. The consultant never gives a verdict: it does not say buy, sell or hold, predict
prices, or promise returns, and the reply ends by handing the decision back to the user.

Guardrails are mechanical (`_clean_text`): a sentence containing a forecast, an instruction to
buy/sell, a number not present in the evidence, or an unknown ticker is dropped, and a link is
kept only if it came from a tool result. If the model is down, or everything it wrote is
rejected, the brief is built deterministically from the same evidence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

from investment_agent.config.settings import get_settings
from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.market.cache import CacheTTL, cache_get, cache_set
from investment_agent.market.macro import get_macro_snapshot
from investment_agent.market.news import get_news
from investment_agent.market.tavily import tavily_search
from investment_agent.research import progress
from investment_agent.research.llm_guard import (
    _FORECAST_RE,
    GENERIC_CAPS,
    allowed_numbers,
    numbers_in,
    tickers_in,
)
from investment_agent.research.sentiment import aggregate_sentiment

logger = logging.getLogger(__name__)

# The chat client gives up after 90 s, and the stock picker itself can take ~20 s, so the whole
# research step is held to TOTAL_BUDGET_SECONDS no matter how slow a tool or model is.
TOTAL_BUDGET_SECONDS = 38.0
GATHER_TIMEOUT_SECONDS = 12.0
MIN_SYNTHESIS_SECONDS = 8.0
NEWS_WINDOW_DAYS = 30
SNIPPET_CHARS = 280
TOOL_CONCURRENCY = 5

HANDOVER = (
    "**The decision is yours.** I research and explain; I don't tell you to buy, sell or hold. "
    "Ask me to dig deeper into any one stock, swap one out, or change the amount."
)

_ADVICE_RE = re.compile(
    r"\b(you should|you must|i recommend|i suggest|we recommend|strong buy|must[- ]buy|buy (?:it|this|now|more)|"
    r"sell (?:it|this|now)|go for|accumulate|add to your portfolio|good time to)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- gathering

# Headlines that are themselves buy/sell calls, price targets or penny-stock promotion: they are
# not shown and not given to the model, so the consultant never repeats them as findings.
_CALL_HEADLINE_RE = re.compile(
    r"\b(target|upside|downside|multibagger|penny|buy|sell|hold|accumulate|top picks?|best stocks?)\b",
    re.IGNORECASE,
)


def _snippet(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1].rstrip() + "…"


def _domain(url: str | None) -> str:
    return (urlparse(url or "").netloc or "web").removeprefix("www.")


async def _stock_news(row: dict[str, Any]) -> dict[str, Any]:
    """Recent news for one stock: Tavily snippets first, Google News RSS headlines if none."""
    symbol = row["symbol"]
    cache_key = f"research:news:{symbol}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    name = row.get("name") or symbol
    tool = "tavily"
    hits = await tavily_search(
        f"{name} ({symbol}) NSE stock results business news",
        topic="news",
        max_results=5,
        days=NEWS_WINDOW_DAYS,
    )
    items = [
        {"title": str(h["title"]).strip(), "url": h.get("url"), "snippet": _snippet(h.get("content"))}
        for h in hits
        if not _CALL_HEADLINE_RE.search(str(h["title"]))
    ]
    if not items:
        tool = "google_news_rss"
        items = [
            {"title": a["title"], "url": a.get("link"), "snippet": ""}
            for a in await get_news(name, limit=8)
            if not _CALL_HEADLINE_RE.search(a["title"])
        ][:5]
    result = {
        "tool": tool if items else None,
        "items": items,
        "sentiment": aggregate_sentiment([{"title": i["title"]} for i in items]),
    }
    if items:
        await cache_set(cache_key, json.dumps(result), CacheTTL.NEWS)
    return result


async def _market_backdrop() -> dict[str, Any]:
    macro, hits = await asyncio.gather(
        get_macro_snapshot(),
        tavily_search(
            "Indian stock market outlook Nifty Sensex this week",
            topic="news",
            max_results=3,
            days=7,
        ),
        return_exceptions=True,
    )
    return {
        "macro": macro if isinstance(macro, dict) else {},
        "headlines": [
            {"title": str(h["title"]).strip(), "url": h.get("url"), "snippet": _snippet(h.get("content"))}
            for h in (hits if isinstance(hits, list) else [])
        ],
    }


async def gather(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run every research tool; a tool that fails simply contributes nothing."""
    gate = asyncio.Semaphore(TOOL_CONCURRENCY)
    names = ", ".join(r["symbol"] for r in rows[:6]) + ("…" if len(rows) > 6 else "")
    progress.emit("search", "Searching the web for recent news", names)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            try:
                return await _stock_news(row)
            except Exception as exc:
                logger.info("News research failed for %s: %s", row["symbol"], exc)
                return {"tool": None, "items": [], "sentiment": aggregate_sentiment([])}

    news_results, backdrop = await asyncio.gather(
        asyncio.gather(*(one(r) for r in rows)), _market_backdrop()
    )
    found = sum(len(r["items"]) for r in news_results) + len(backdrop["headlines"])
    progress.emit("search", "Searched the web for recent news", f"{found} articles found", done=True)
    progress.emit("data", "Checking factor scores and macro data", done=True)
    tools = {"portfolio_factor_scores"}
    if backdrop["macro"]:
        tools.add("macro_snapshot")
    for result in news_results:
        if result["tool"]:
            tools.add(result["tool"])
    if backdrop["headlines"]:
        tools.add("tavily")
    return {
        "news": {r["symbol"]: res for r, res in zip(rows, news_results, strict=True)},
        "market": backdrop,
        "tools_used": sorted(tools),
    }


# ---------------------------------------------------------------- evidence for the model


def _evidence(rows: list[dict[str, Any]], gathered: dict[str, Any]) -> dict[str, Any]:
    stocks = []
    for row in rows:
        news = gathered["news"][row["symbol"]]
        stocks.append(
            {
                "symbol": row["symbol"],
                "name": row.get("name"),
                "sector": row.get("sector"),
                "market_cap_band": row.get("market_cap_band"),
                "overall_score_out_of_100": row.get("score"),
                "strongest_factors": row.get("why") or [],
                "signals": row.get("signals") or {},
                "news_sentiment": news["sentiment"],
                "recent_news": news["items"],
            }
        )
    return {
        "news_window_days": NEWS_WINDOW_DAYS,
        "stocks": stocks,
        "market_backdrop": gathered["market"],
    }


PROMPT = """You are a careful research consultant for a first-time Indian investor. A stock list was \
already chosen by a scoring model. Your job is to explain, from the EVIDENCE only, why each stock \
is on the list and what the person should weigh, so they can decide for themselves.

Return ONLY JSON of this shape:
{{"market": "<1-2 sentences on the backdrop, or empty>",
  "stocks": {{"<SYMBOL>": {{
     "why_picked": "<1-2 sentences, plain English, from strongest_factors / signals>",
     "in_favour": ["<short point>", ...],
     "watch_out": ["<short risk or concern, incl. any negative news>", ...],
     "recent": [{{"text": "<what the news says, one sentence>", "url": "<url copied from recent_news>"}}],
     "check_before_deciding": ["<one thing the person should look at themselves>"]}}}}}}

Rules:
- Use only facts, numbers and links that appear in the EVIDENCE. Never invent a figure, company or URL.
- Explain jargon briefly. Maximum 2 items in each list, 1-2 recent items per stock.
- Be balanced: every stock needs at least one watch_out (concentration, valuation, volatility, sector risk).
- Do NOT say buy, sell or hold; do NOT say "you should"; do NOT predict prices or promise returns; \
no targets. You inform, the person decides.
- If recent_news is empty, say so in watch_out ("no recent news found") and leave recent empty.

EVIDENCE:
{evidence}
"""


def _parse_json(raw: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------- guardrail


class _Check:
    def __init__(self, evidence: dict[str, Any], symbols: list[str]) -> None:
        text = json.dumps(evidence)
        self.numbers = allowed_numbers(evidence)
        self.tickers = {s.upper() for s in symbols} | set(tickers_in(text)) | GENERIC_CAPS
        self.urls = {
            item["url"]
            for stock in evidence["stocks"]
            for item in stock["recent_news"]
            if item.get("url")
        } | {h["url"] for h in evidence["market_backdrop"]["headlines"] if h.get("url")}

    def text(self, value: Any, max_len: int = 400) -> str | None:
        """The sentence if it passes every check, else None (it is dropped)."""
        if not isinstance(value, str) or not value.strip() or len(value) > max_len:
            return None
        value = value.strip()
        if _FORECAST_RE.search(value) or _ADVICE_RE.search(value):
            return None
        if any(t not in self.tickers for t in tickers_in(value)):
            return None
        if any(not any(abs(n - a) < 1e-9 for a in self.numbers) for n in numbers_in(value)):
            return None
        return value

    def texts(self, values: Any, limit: int = 2) -> list[str]:
        if not isinstance(values, list):
            return []
        kept = (self.text(v) for v in values)
        return [t for t in kept if t][:limit]

    def recent(self, values: Any) -> list[dict[str, str | None]]:
        out: list[dict[str, str | None]] = []
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            text = self.text(item.get("text"))
            if text:
                url = item.get("url")
                out.append({"text": text, "url": url if url in self.urls else None})
        return out[:2]


def _fallback_brief(row: dict[str, Any], news: dict[str, Any]) -> dict[str, Any]:
    sentiment = news["sentiment"]
    why = row.get("why") or []
    watch = [
        "Any single stock can fall sharply; it is one company's business, not the whole market.",
    ]
    if sentiment["label"] == "NEGATIVE":
        watch.insert(0, "Recent headlines lean negative, so read them before deciding.")
    elif not news["items"]:
        watch.insert(0, "No recent news was found, so there is little fresh information beyond the scores.")
    return {
        "why_picked": ("Ranked well on " + ", ".join(why) + ".") if why else "It scored well in the screening.",
        "in_favour": [],
        "watch_out": watch[:2],
        "recent": [{"text": i["title"], "url": i.get("url")} for i in news["items"][:2]],
        "check_before_deciding": ["Read the company's latest results and the news links above."],
    }


def _model_tiers() -> tuple[str, ...]:
    """Primary first, then cheap, unless both resolve to the same model (a retry would be a repeat)."""
    settings = get_settings()
    same = (settings.PRIMARY_LLM_PROVIDER, settings.PRIMARY_LLM_MODEL) == (
        settings.CHEAP_LLM_PROVIDER,
        settings.CHEAP_LLM_MODEL,
    )
    return ("primary",) if same else ("primary", "cheap")


async def _synthesise(evidence: dict[str, Any], deadline: float) -> dict[str, Any] | None:
    prompt = PROMPT.format(evidence=json.dumps(evidence, ensure_ascii=False))
    for tier in _model_tiers():
        remaining = deadline - time.monotonic()
        if remaining < MIN_SYNTHESIS_SECONDS:
            break
        try:
            model = get_llm(tier)
            reply = await asyncio.wait_for(model.ainvoke(prompt), timeout=remaining)
            parsed = _parse_json(extract_text(reply.content))
            if parsed:
                return parsed
        except Exception as exc:
            logger.info("Research synthesis unavailable on tier %s: %s", tier, exc)
    return None


# ---------------------------------------------------------------- public API


def _sources(briefs: dict[str, dict[str, Any]], backdrop_urls: list[str]) -> list[dict[str, Any]]:
    from investment_agent.research.evidence import Evidence, SourceType

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for symbol, brief in briefs.items():
        for item in brief["recent"]:
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(
                Evidence(
                    claim=f"Recent news on {symbol}",
                    source_name=_domain(url),
                    source_url=url,
                    source_type=SourceType.REPUTABLE_NEWS,
                ).model_dump(mode="json")
            )
    for url in backdrop_urls:
        if url not in seen:
            seen.add(url)
            out.append(
                Evidence(
                    claim="Indian market backdrop",
                    source_name=_domain(url),
                    source_url=url,
                    source_type=SourceType.REPUTABLE_NEWS,
                ).model_dump(mode="json")
            )
    return out


async def research_stocks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Research brief for each plan row. Never raises; status is OK or UNAVAILABLE."""
    if not rows:
        return {"status": "UNAVAILABLE", "briefs": {}, "tools_used": [], "sources": []}
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS
    try:
        gathered = await asyncio.wait_for(gather(rows), timeout=GATHER_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("Research gathering failed: %s", exc)
        return {"status": "UNAVAILABLE", "briefs": {}, "tools_used": [], "sources": []}

    progress.emit("write", "Writing research notes", "Weighing the evidence for each stock")
    evidence = _evidence(rows, gathered)
    symbols = [r["symbol"] for r in rows]
    check = _Check(evidence, symbols)
    written = await _synthesise(evidence, deadline)
    written_stocks = written.get("stocks") if written else None
    if not isinstance(written_stocks, dict):
        written_stocks = {}

    briefs: dict[str, dict[str, Any]] = {}
    ai_written = 0
    for row in rows:
        symbol = row["symbol"]
        raw = written_stocks.get(symbol)
        fallback = _fallback_brief(row, gathered["news"][symbol])
        if not isinstance(raw, dict):
            briefs[symbol] = {**fallback, "written_by": "reviewed"}
            continue
        brief = {
            "why_picked": check.text(raw.get("why_picked")) or fallback["why_picked"],
            "in_favour": check.texts(raw.get("in_favour")),
            "watch_out": check.texts(raw.get("watch_out")) or fallback["watch_out"],
            "recent": check.recent(raw.get("recent")) or fallback["recent"],
            "check_before_deciding": check.texts(raw.get("check_before_deciding"), 1)
            or fallback["check_before_deciding"],
            "written_by": "ai",
        }
        ai_written += 1
        briefs[symbol] = brief

    progress.emit("write", "Wrote research notes", "Checked against safety rules", done=True)
    market_text = check.text(written.get("market")) if written else None
    backdrop = gathered["market"]
    return {
        "status": "OK",
        "briefs": briefs,
        "market": market_text,
        "tools_used": gathered["tools_used"],
        "web_search": bool(get_settings().TAVILY_API_KEY),
        "ai_written": ai_written,
        "sources": _sources(briefs, [h["url"] for h in backdrop["headlines"] if h.get("url")]),
    }


def _bullets(items: list[str]) -> str:
    return "\n".join(f"  - {i}" for i in items)


def render(rows: list[dict[str, Any]], research: dict[str, Any]) -> str:
    """Markdown research notes for the chat; empty string when no research is available."""
    if research.get("status") != "OK":
        return ""
    parts = ["### Research notes"]
    if research.get("market"):
        parts.append(f"**Market backdrop:** {research['market']}")
    for i, row in enumerate(rows, start=1):
        brief = research["briefs"].get(row["symbol"])
        if not brief:
            continue
        lines = [f"**{i}. {row['symbol']}** ({row['sector']})", f"- **Why it made the list:** {brief['why_picked']}"]
        if brief["in_favour"]:
            lines.append("- **In its favour:**\n" + _bullets(brief["in_favour"]))
        lines.append("- **Watch out for:**\n" + _bullets(brief["watch_out"]))
        if brief["recent"]:
            recent = [
                f"{r['text']} ([{_domain(r['url'])}]({r['url']}))" if r.get("url") else r["text"]
                for r in brief["recent"]
            ]
            lines.append("- **In the news:**\n" + _bullets(recent))
        lines.append("- **Before you decide:** " + brief["check_before_deciding"][0])
        parts.append("\n".join(lines))
    web = "web search (Tavily)" if research.get("web_search") else "news headlines only (web search is off)"
    parts.append(f"*Researched using {web}, factor scores and macro data. Past information, not a forecast.*")
    parts.append(HANDOVER)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- research-only answers

FINANCE_DOMAINS = [
    "economictimes.indiatimes.com",
    "moneycontrol.com",
    "livemint.com",
    "business-standard.com",
    "thehindubusinessline.com",
    "nseindia.com",
    "bseindia.com",
    "sebi.gov.in",
    "rbi.org.in",
    "amfiindia.com",
    "incometax.gov.in",
    "screener.in",
]

# Questions whose answer changes over time: a model's memory is stale on these, so they search
# even when the user has not switched Research on.
_FRESH_RE = re.compile(
    r"\b(today|tonight|latest|current(?:ly)?|right now|now|this (?:week|month|year)|recent(?:ly)?|"
    r"new rule|news|20\d\d|tax|ltcg|stcg|rate|circular|ban)\b",
    re.IGNORECASE,
)


def needs_fresh_facts(message: str) -> bool:
    return bool(_FRESH_RE.search(message))


ANSWER_PROMPT = """You are a careful research assistant for Indian stock-market investors. Answer \
the QUESTION using ONLY the numbered SOURCES below. If the question is not about stocks, the \
stock market, mutual funds, ETFs or investing, set in_scope to false.

Return ONLY JSON: {{"in_scope": true|false, "answer": "<Markdown>"}}

Answer format: a one- or two-sentence direct answer, then 3-5 short bullet points. Cite every \
claim with its source number in square brackets, like [2]. Say plainly when the sources do not \
cover something. Explain jargon briefly.
Rules: use only facts and numbers present in the SOURCES; never name a security that is not in \
the sources; do NOT say buy, sell or hold or "you should"; do NOT predict prices or promise \
returns. You inform, the person decides.

QUESTION: {question}
{context}
SOURCES:
{sources}
"""


async def _finance_search(question: str, *, fresh: bool) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {"topic": "news" if fresh else "general", "max_results": 6, "days": 30}
    hits = await tavily_search(question, include_domains=FINANCE_DOMAINS, **kwargs)
    if len(hits) < 2:  # the trusted list had little: widen to the whole web
        hits = await tavily_search(question, **kwargs)
    return hits


def _cite(line: str, urls: dict[int, str]) -> str:
    return re.sub(
        r"\[(\d+)\]",
        lambda m: f"[{m.group(1)}]({urls[int(m.group(1))]})" if int(m.group(1)) in urls else "",
        line,
    )


async def research_answer(question: str, context: str = "") -> dict[str, Any]:
    """Answer a stock/market question from live web sources, with citations.

    Returns {"status": "OK", "text", "sources", "tools_used"} or
    {"status": "OUT_OF_SCOPE"} / {"status": "UNAVAILABLE", "reason"}.
    """
    if not get_settings().TAVILY_API_KEY:
        return {"status": "UNAVAILABLE", "reason": "no_key"}
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS
    progress.emit("understand", "Understanding your question", done=True)
    progress.emit("search", "Searching trusted finance sources", question[:80])
    fresh = needs_fresh_facts(question)
    try:
        hits = await asyncio.wait_for(_finance_search(question, fresh=fresh), GATHER_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("Research search failed: %s", exc)
        return {"status": "UNAVAILABLE", "reason": "search_failed"}
    if not hits:
        progress.emit("search", "Searched the web", "No relevant sources found", done=True)
        return {"status": "UNAVAILABLE", "reason": "no_results"}
    hits = [h for h in hits if not _CALL_HEADLINE_RE.search(str(h["title"]))] or hits
    sources = [
        {"id": i, "title": str(h["title"]).strip(), "url": h.get("url"), "snippet": _snippet(h.get("content"))}
        for i, h in enumerate(hits[:6], start=1)
    ]
    domains = ", ".join(sorted({_domain(s["url"]) for s in sources}))
    progress.emit("search", "Searched trusted finance sources", f"{len(sources)} sources", done=True)
    progress.emit("read", "Reading sources", domains)

    evidence = {"stocks": [{"recent_news": sources}], "market_backdrop": {"headlines": []}, "sources": sources}
    check = _Check(evidence, [])
    urls = {s["id"]: s["url"] for s in sources if s["url"]}
    answer = None
    for tier in _model_tiers():
        remaining = deadline - time.monotonic()
        if remaining < MIN_SYNTHESIS_SECONDS:
            break
        try:
            progress.emit("write", "Writing the answer", "Citing each claim")
            prompt = ANSWER_PROMPT.format(
                question=question,
                context=f"CONVERSATION SO FAR:\n{context}\n" if context else "",
                sources=json.dumps(sources, ensure_ascii=False),
            )
            reply = await asyncio.wait_for(get_llm(tier).ainvoke(prompt), timeout=remaining)
            answer = _parse_json(extract_text(reply.content))
            if answer:
                break
        except Exception as exc:
            logger.info("Research answer unavailable on tier %s: %s", tier, exc)
    if answer and answer.get("in_scope") is False:
        return {"status": "OUT_OF_SCOPE"}

    kept: list[str] = []
    for line in str(answer.get("answer", "") if answer else "").splitlines():
        if not line.strip() or check.text(re.sub(r"\[\d+\]", "", line), max_len=600):
            kept.append(_cite(line, urls))
    body = "\n".join(kept).strip()
    reviewed = not body
    if reviewed:
        body = "I found these recent sources on your question:\n" + "\n".join(
            f"- {s['title']} ([{_domain(s['url'])}]({s['url']}))" for s in sources[:4] if s["url"]
        )
    progress.emit("write", "Wrote the answer", "Checked against safety rules", done=True)
    footer = "\n".join(
        f"{s['id']}. [{s['title']}]({s['url']}) - {_domain(s['url'])}" for s in sources if s["url"]
    )
    from investment_agent.research.evidence import Evidence, SourceType

    return {
        "status": "OK",
        "text": f"{body}\n\n**Sources**\n{footer}\n\n{HANDOVER}",
        "sources": [
            Evidence(
                claim="Web source for the answer",
                source_name=_domain(s["url"]),
                source_url=s["url"],
                source_type=SourceType.REPUTABLE_NEWS,
            ).model_dump(mode="json")
            for s in sources
            if s["url"]
        ],
        "tools_used": ["tavily"],
        "written_by": "reviewed" if reviewed else "ai",
    }
