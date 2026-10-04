"""Deterministic, lexicon-based news-sentiment scoring (Workstream A, Step 4 / F4).

This is **not** an LLM/ML sentiment classifier — it is a documented keyword lexicon
scored in Python, in keeping with this project's "Python computes every number, the LLM
only narrates" rule (see `research/stock_score.py`, `portfolio/scoring.py` for the same
invariant applied elsewhere). It replaces Step 2's narrower keyword screen — which only
looked at exchange-filing subjects (`graph/nodes.py::_FILING_RISK_KEYWORDS`) — with a
broader one that runs over real news headlines (`market/news.py`).

Being a lexicon, this is a coarse, auditable signal: how many positive/negative
finance-news words appear in recent headlines, not a claim of true natural-language
understanding. Every number here is reproducible from the same input headlines.
"""

from __future__ import annotations

import re
from typing import Any

POSITIVE_WORDS = (
    "surge",
    "surges",
    "rally",
    "rallies",
    "soar",
    "soars",
    "jump",
    "jumps",
    "gain",
    "gains",
    "profit",
    "profits",
    "growth",
    "beat",
    "beats",
    "upgrade",
    "upgrades",
    "upgraded",
    "record high",
    "expansion",
    "strong",
    "robust",
    "bullish",
    "outperform",
    "buyback",
    "dividend",
    "approval",
    "approves",
    "award",
    "awarded",
    "stake buy",
    "raises",
    "raised guidance",
    "wins order",
    "wins contract",
)

NEGATIVE_WORDS = (
    "crash",
    "crashes",
    "plunge",
    "plunges",
    "slump",
    "slumps",
    "tumble",
    "tumbles",
    "loss",
    "losses",
    "fraud",
    "probe",
    "investigation",
    "downgrade",
    "downgrades",
    "downgraded",
    "default",
    "insolvency",
    "resignation",
    "resigns",
    "scam",
    "raid",
    "lawsuit",
    "ban",
    "banned",
    "fine",
    "fined",
    "penalty",
    "layoff",
    "layoffs",
    "strike",
    "decline",
    "declines",
    "bearish",
    "sell-off",
    "selloff",
    "weak",
    "miss",
    "misses",
    "cut",
    "cuts",
    "scrutiny",
)


def _compile_word_boundary_patterns(words: tuple[str, ...]) -> list[re.Pattern[str]]:
    # `\b...\b` so "ban" doesn't match inside "bank", "cut" inside "circuit", etc. — a
    # plain substring check produced exactly that false positive during development.
    return [re.compile(rf"\b{re.escape(word)}\b") for word in words]


_POSITIVE_PATTERNS = _compile_word_boundary_patterns(POSITIVE_WORDS)
_NEGATIVE_PATTERNS = _compile_word_boundary_patterns(NEGATIVE_WORDS)


def score_headline(text: str) -> int:
    """Positive word count minus negative word count in `text`. Zero for empty/neutral."""
    lowered = text.lower()
    positive = sum(1 for pattern in _POSITIVE_PATTERNS if pattern.search(lowered))
    negative = sum(1 for pattern in _NEGATIVE_PATTERNS if pattern.search(lowered))
    return positive - negative


def aggregate_sentiment(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-headline scores into a label + counts. `DATA_UNAVAILABLE` (not a
    fabricated NEUTRAL) when there are no articles to score at all."""
    if not articles:
        return {
            "label": "DATA_UNAVAILABLE",
            "score": None,
            "positive_count": 0,
            "negative_count": 0,
            "total_articles": 0,
        }

    scored = [score_headline(article.get("title") or "") for article in articles]
    net = sum(scored)
    label = "POSITIVE" if net > 0 else "NEGATIVE" if net < 0 else "NEUTRAL"

    return {
        "label": label,
        "score": net,
        "positive_count": sum(1 for s in scored if s > 0),
        "negative_count": sum(1 for s in scored if s < 0),
        "total_articles": len(articles),
    }
