"""Education answers: "what is an ETF?", "explain SIP", "how does the market work?".

Reviewed glossary entries are returned verbatim, with no model and no market data, so they
cannot contain a price, a return or a ticker. A concept outside the glossary may be answered
by the cheap model, but only under a system prompt that forbids prices, returns, tickers and
recommendations, and the reply is discarded unless it passes a mechanical check for exactly
those things. If the model is down or its reply is rejected, the user gets the list of terms
we can explain instead of a guess.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.research.evidence import Evidence, SourceType
from investment_agent.research.formatting import inr
from investment_agent.research.glossary import (
    GLOSSARY,
    Comparison,
    GlossaryEntry,
    compare_terms,
    entry_by_term,
    find_term,
    find_terms,
    split_comparison_sides,
)

logger = logging.getLogger(__name__)

EDUCATION_SYSTEM_PROMPT = (
    "You explain one investing concept to someone who has never invested, in 3 to 5 short "
    "plain sentences with no jargon left unexplained. You must NOT mention any price, "
    "index level, percentage, return or rupee amount for a real security, NOT name any "
    "company or ticker, and NOT recommend buying, selling or holding anything or promise any "
    "outcome. If the question is not about how investing or markets work, say you can only "
    "explain investing concepts."
)

_DISALLOWED_PATTERNS = (
    re.compile(r"[%₹$]|\brs\.?\s*\d|\binr\b|\brupees?\b|\bpercent\b", re.IGNORECASE),
    re.compile(r"\d"),
    re.compile(
        r"\b(you should (?:buy|sell|hold|invest)|i recommend|i suggest you|guaranteed?|"
        r"will (?:earn|return|grow|rise|double)|target price|sure[- ]shot)\b",
        re.IGNORECASE,
    ),
)
# Upper-case words that are acronyms for concepts, not company tickers.
_ALLOWED_ACRONYMS = frozenset(
    {"ETF", "SIP", "NAV", "IPO", "NSE", "BSE", "SEBI", "RBI", "ELSS", "PE", "ROE", "GDP", "EMI", "KYC", "PAN", "AMC", "FD", "RD", "I"}
)

NEXT_STEP_BY_TERM = {
    "SIP": "Plan a ₹5,000 monthly SIP",
    "ETF": "Plan a ₹5,000 monthly SIP",
    "Mutual fund": "Plan a ₹5,000 monthly SIP",
    "Index fund": "Plan a ₹5,000 monthly SIP",
    "NAV": "Plan a ₹5,000 monthly SIP",
    "Expense ratio": "Plan a ₹5,000 monthly SIP",
    "ELSS": "Plan a ₹5,000 monthly SIP",
}
DEFAULT_NEXT_STEP = "Suggest 10 stocks for ₹10,000"


def passes_education_check(text: str) -> bool:
    """True only if a model-written explanation contains no figures, tickers or advice."""
    if not text.strip():
        return False
    if any(pattern.search(text) for pattern in _DISALLOWED_PATTERNS):
        return False
    return all(
        word in _ALLOWED_ACRONYMS for word in re.findall(r"\b[A-Z]{2,}\b", text)
    )


def next_step_chip(term: str | None, amount_inr: float | None) -> str:
    if amount_inr:
        shown = inr(amount_inr)
        if term in NEXT_STEP_BY_TERM:
            return f"Plan a {shown} monthly SIP"
        return f"Suggest 10 stocks for {shown}"
    return NEXT_STEP_BY_TERM.get(term or "", DEFAULT_NEXT_STEP)


def _glossary_sources(entry: GlossaryEntry) -> list[dict[str, Any]]:
    return [
        Evidence(
            claim=f"Definition of {entry.term}",
            source_name="Curated beginner glossary (reviewed definitions)",
            source_type=SourceType.OTHER,
        ).model_dump(mode="json")
    ]


def glossary_answer(entry: GlossaryEntry, amount_inr: float | None) -> dict[str, Any]:
    return {
        "text": f"{entry.definition}\n\nExample: {entry.example}",
        "glossary": {"term": entry.term, "definition": entry.definition, "example": entry.example},
        "suggestions": [next_step_chip(entry.term, amount_inr)],
        "sources": _glossary_sources(entry),
        "source": "glossary",
    }


async def _llm_explain(question: str) -> str | None:
    try:
        model = get_llm("cheap")
        reply = await model.ainvoke(f"{EDUCATION_SYSTEM_PROMPT}\n\nQuestion: {question}")
        text = extract_text(reply.content).strip()
    except Exception as exc:
        logger.info("Education model unavailable: %s", exc)
        return None
    if not passes_education_check(text):
        logger.info("Education model reply rejected by the content check")
        return None
    return text


def _teachable_chips() -> list[str]:
    return [f"What is {name}?" for name in ("an ETF", "a SIP", "a mutual fund", "NAV")]


async def explain(message: str, concept: str | None, amount_inr: float | None) -> dict[str, Any]:
    """Answer an education question. Never needs amount, horizon or any market data."""
    entry = find_term(message) or (entry_by_term(concept) if concept else None)
    if entry is not None:
        return glossary_answer(entry, amount_inr)
    text = await _llm_explain(message)
    if text is not None:
        return {
            "text": text,
            "suggestions": [next_step_chip(None, amount_inr)],
            "sources": [],
            "source": "llm",
        }
    known = ", ".join(entry.term for entry in GLOSSARY[:8])
    return {
        "text": (
            "I don't have a reviewed explanation for that yet, and I'd rather not guess. "
            f"I can explain terms such as {known}. Which would you like?"
        ),
        "suggestions": _teachable_chips(),
        "sources": [],
        "source": "none",
    }


COMPARE_SYSTEM_PROMPT = (
    "You explain the difference between two investing concepts to someone who has never "
    "invested, in 4 to 6 short plain sentences with no jargon left unexplained. You must NOT "
    "mention any price, index level, percentage, return, fee or rupee amount, NOT name any "
    "company or ticker, and NOT recommend buying, selling or holding anything or promise any "
    "outcome. If the question is not about how investing or markets work, say you can only "
    "explain investing concepts."
)


def _comparison_sources(comparison: Comparison) -> list[dict[str, Any]]:
    name = (
        "Curated beginner comparison (reviewed text)"
        if comparison.curated
        else "Curated beginner glossary (reviewed definitions)"
    )
    return [
        Evidence(
            claim=f"Comparison: {comparison.title}", source_name=name, source_type=SourceType.OTHER
        ).model_dump(mode="json")
    ]


async def _llm_compare(message: str) -> str | None:
    try:
        model = get_llm("cheap")
        reply = await model.ainvoke(f"{COMPARE_SYSTEM_PROMPT}\n\nQuestion: {message}")
        text = extract_text(reply.content).strip()
    except Exception as exc:
        logger.info("Comparison model unavailable: %s", exc)
        return None
    if not passes_education_check(text):
        logger.info("Comparison model reply rejected by the content check")
        return None
    return text


async def compare(message: str, term_a: str | None, term_b: str | None) -> dict[str, Any]:
    """Answer "difference between X and Y". A curated table when we have one, otherwise one
    composed from the two glossary definitions, otherwise a guarded model answer; the model
    never sees or returns prices, returns or tickers. The message is re-parsed here, so the
    slot values are only a hint if the phrasing was unusual."""
    sides = split_comparison_sides(message) or [side for side in (term_a, term_b) if side]
    if len(sides) < 2:
        sides = [entry.term for entry in find_terms(message)[:2]]
    comparison = compare_terms(sides) if len(sides) >= 2 else None
    if comparison is not None:
        return {
            "text": comparison.as_text(),
            "comparison": comparison.as_dict(),
            "suggestions": list(comparison.suggestions),
            "sources": _comparison_sources(comparison),
            "source": "glossary",
        }
    text = await _llm_compare(message)
    if text is not None:
        return {
            "text": text,
            "suggestions": [next_step_chip(None, None), "What is an ETF?"],
            "sources": [],
            "source": "llm",
        }
    known = [entry.term for entry in find_terms(message)[:2]]
    chips = [f"What is {term}?" for term in known] or _teachable_chips()
    return {
        "text": (
            "I don't have a reviewed comparison for those two yet, and I'd rather not guess. "
            "I can explain each one on its own, so ask about either."
        ),
        "suggestions": chips,
        "sources": [],
        "source": "none",
    }
