"""Grounding check for model-written text.

A model may phrase a result our code already computed, but it may not add to it. Before any
model sentence reaches the user, `is_grounded` verifies mechanically that

- every ticker-like token is one of the symbols in the structured result,
- every number appears in the structured result (as given, or rounded to 0-2 decimals), and
- no forecast language (targets, expected returns, guarantees, "will rise") slipped in.

If any check fails the text is discarded and the caller uses its deterministic template.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&]{1,11}\b")
_FORECAST_RE = re.compile(
    r"\b(target price|expected return|expect(?:ed)? to (?:rise|grow|return|double)|guarantee[ds]?|"
    r"will (?:rise|grow|double|outperform|return|earn|go up)|price target|sure[- ]shot|can't lose|"
    r"buy now|sell now|multibagger)\b",
    re.IGNORECASE,
)
# Words that are written in capitals but are not securities.
GENERIC_CAPS = frozenset(
    {"INR", "NSE", "BSE", "SIP", "ETF", "SEBI", "IPO", "ROE", "ROCE", "PE", "AI", "NAV", "DP", "RS", "I", "A"}
)


def _walk_numbers(value: Any, out: set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        out.add(float(value))
    elif isinstance(value, str):
        for token in _NUMBER_RE.findall(value):
            out.add(float(token.replace(",", "")))
    elif isinstance(value, dict):
        for item in value.values():
            _walk_numbers(item, out)
    elif isinstance(value, (list, tuple, set)):
        out.add(float(len(value)))
        for item in value:
            _walk_numbers(item, out)


def allowed_numbers(structured: Any) -> set[float]:
    """Every figure in the result, plus its 0/1/2-decimal roundings and sizes of its lists."""
    raw: set[float] = set()
    _walk_numbers(structured, raw)
    allowed: set[float] = set()
    for number in raw:
        allowed.add(number)
        for places in (0, 1, 2):
            allowed.add(round(number, places))
    return allowed


def numbers_in(text: str) -> list[float]:
    # A trailing "." or "," belongs to the sentence, not the number.
    return [float(t.rstrip(".,").replace(",", "")) for t in _NUMBER_RE.findall(text)]


def tickers_in(text: str) -> list[str]:
    return [t for t in _TICKER_RE.findall(text) if t not in GENERIC_CAPS]


def is_grounded(text: str, structured: Any, allowed_tickers: Iterable[str]) -> bool:
    """True only if `text` introduces no ticker, number or forecast absent from `structured`."""
    if not text.strip() or _FORECAST_RE.search(text):
        return False
    symbols = {s.upper() for s in allowed_tickers}
    if any(ticker not in symbols for ticker in tickers_in(text)):
        return False
    allowed = allowed_numbers(structured)
    return all(any(abs(n - a) < 1e-9 for a in allowed) for n in numbers_in(text))
