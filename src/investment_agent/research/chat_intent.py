"""Structured intent + slot extraction for the chat.

One pass turns a free-text message into a validated `Extraction` (an intent from a closed
list plus typed slots). Two producers feed it:

1. A cheap-tier LLM asked for JSON only, validated by pydantic. Free-form model text never
   reaches control flow: anything that does not validate is discarded.
2. Deterministic rules (regexes + the curated glossary). They always run, supply every slot
   the model missed, and are the whole answer when the model is unavailable or invalid.

Tickers are never taken from the model or from "any all-caps word". A symbol exists only if
it matches the real security master (exact symbol or company-name search), see
`resolve_symbols`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from investment_agent.llm.factory import extract_text, get_llm
from investment_agent.research.glossary import (
    GLOSSARY_ALIAS_WORDS,
    asks_for_definition,
    find_term,
    is_bare_term,
)

logger = logging.getLogger(__name__)

Intent = Literal[
    "education",
    "stock_list",
    "stock_single",
    "plan_sip_fund",
    "plan_sip_etf",
    "fund_list",
    "market_overview",
    "portfolio_help",
    "answer",
    "off_topic",
    "unclear",
]
RiskProfile = Literal["conservative", "moderate", "aggressive"]
AmountKind = Literal["lump_sum", "monthly"]
Experience = Literal["beginner", "intermediate"]

INTENTS: tuple[str, ...] = (
    "education",
    "stock_list",
    "stock_single",
    "plan_sip_fund",
    "plan_sip_etf",
    "fund_list",
    "market_overview",
    "portfolio_help",
    "answer",
    "off_topic",
    "unclear",
)


class Slots(BaseModel):
    amount_inr: float | None = Field(default=None, gt=0)
    amount_kind: AmountKind | None = None
    horizon_years: int | None = Field(default=None, ge=1, le=50)
    risk_profile: RiskProfile | None = None
    stock_count: int | None = Field(default=None, ge=1, le=50)
    stock_count_min: int | None = Field(default=None, ge=1, le=50)
    symbol: str | None = None
    concept: str | None = None
    experience_level: Experience | None = None
    sectors_wanted: list[str] = Field(default_factory=list)

    def provided(self) -> dict[str, Any]:
        """Only the slots that actually carry a value."""
        return {k: v for k, v in self.model_dump().items() if v not in (None, [], "")}


class _LLMReply(BaseModel):
    intent: Intent
    slots: Slots = Field(default_factory=Slots)


class SymbolMatch(BaseModel):
    symbol: str | None = None
    candidates: list[dict[str, str]] = Field(default_factory=list)


class Extraction(BaseModel):
    intent: Intent
    slots: Slots
    symbol_candidates: list[dict[str, str]] = Field(default_factory=list)
    source: Literal["llm", "rules"] = "rules"


# --------------------------------------------------------------------------- symbols

_STOP_SYMBOL_TOKENS = frozenset(
    {
        "OK", "OKAY", "YES", "NO", "NOPE", "YEP", "YEAH", "HI", "HELLO", "HEY", "THANKS", "THANK",
        "THE", "AND", "FOR", "ARE", "NOT", "BUT", "CAN", "YOU", "ALL", "ANY", "NEW", "NOW", "ONE",
        "TWO", "HOW", "WHY", "WHAT", "WHO", "WHEN", "WITH", "THIS", "THAT", "FROM", "HAVE", "GIVE",
        "ME", "MY", "AM", "IS", "IT", "AN", "AS", "AT", "BE", "BY", "DO", "IF", "IN", "OF", "ON",
        "OR", "SO", "TO", "UP", "US", "WE", "I", "A", "SURE", "FINE", "GOOD", "BEST", "TOP", "BUY",
        "SELL", "HOLD", "SAFE", "LOW", "HIGH", "SOME", "MORE", "LESS", "STOP", "START", "HELP",
        "AI", "NSE", "BSE", "SEBI", "RBI", "INR", "RS", "IPO", "SIP", "ETF", "NAV", "ELSS", "PE",
        "ROE", "MF", "LTCG", "STCG", "DEMAT", "TER", "UPI", "KYC", "PAN", "GST", "EPS", "FD",
        "GOLD", "BOND", "FUND", "FUNDS", "STOCK", "STOCKS", "SHARE", "SHARES", "MARKET", "RISK",
        "SAFER", "ABOUT", "TELL", "SHOW", "LIST", "PLAN", "OVER", "YEARS", "YEAR", "MONTH",
    }
    | GLOSSARY_ALIAS_WORDS
)

_STOP_NAME_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "is", "are", "i", "me", "my",
        "we", "you", "it", "its", "this", "that", "what", "which", "who", "how", "why", "when",
        "should", "would", "could", "can", "do", "does", "am", "be", "have", "has", "want", "need",
        "buy", "sell", "hold", "invest", "investing", "investment", "about", "tell", "show", "give",
        "list", "suggest", "recommend", "good", "best", "top", "some", "any", "new", "with", "from",
        "stock", "stocks", "share", "shares", "market", "company", "companies", "fund", "funds",
        "etf", "sip", "mutual", "plan", "rupees", "rupee", "rs", "inr", "years", "year", "month",
        "monthly", "per", "price", "now", "today", "please", "thanks", "ok", "okay", "yes", "no",
        "bank", "ltd", "limited", "india", "indian", "industries", "corporation", "corp", "co",
        "future", "potential", "current", "beginner", "start", "just", "also", "much", "many",
        "each", "make", "not", "sure", "safe", "safer", "risk", "high", "low", "over", "next",
        "long", "term", "short", "lump", "sum", "total", "money", "amount", "budget",
    }
)
_NAME_NOISE = frozenset({"ltd", "limited", "inc", "corp", "corporation", "co", "company", "the", "of"})
_LOWERCASE_CONTEXT_RE = re.compile(
    r"\b(buy|sell|hold|price of|about|stock|share|should i|good|outlook|invest in|analy[sz]e)\b",
    re.IGNORECASE,
)


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in _NAME_NOISE]


def _window_matches(window: list[str], name_tokens: list[str]) -> bool:
    for word in window:
        if word in name_tokens:
            continue
        if len(word) >= 4 and any(token.startswith(word) for token in name_tokens):
            continue
        return False
    return True


def search_universe(query: str, master: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
    """Company-name / symbol search over the real security master (never invents entries)."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in _STOP_NAME_WORDS]
    if not tokens:
        return []
    matches: list[dict[str, str]] = []
    for entry in master:
        symbol = entry["symbol"]
        name_tokens = _name_tokens(entry.get("name") or "")
        if symbol.lower() in tokens or (
            name_tokens and _window_matches(tokens, name_tokens) and any(len(t) >= 3 for t in tokens)
        ):
            matches.append(entry)
    matches.sort(key=lambda e: (e["symbol"].lower() not in tokens, e["symbol"]))
    return matches[:limit]


def resolve_symbols(message: str, master: list[dict[str, str]]) -> SymbolMatch:
    """Find the security the user means, only from `master`.

    Exact symbol first (an upper-case token as typed, or a lower-case one when the message
    talks about buying/stocks), then company-name windows of 3, 2 and 1 words. Common words
    and finance jargon are never treated as tickers, so "OK", "YES" or "NO" resolve to nothing.
    """
    if not master:
        return SymbolMatch()
    by_symbol = {entry["symbol"].upper(): entry for entry in master}
    raw_tokens = re.findall(r"[A-Za-z0-9&]+(?:[-.][A-Za-z0-9&]+)*", message)
    has_context = _LOWERCASE_CONTEXT_RE.search(message) is not None
    for token in raw_tokens:
        upper = token.upper()
        if upper in _STOP_SYMBOL_TOKENS or len(upper) < 2 or upper not in by_symbol:
            continue
        if token.isupper() or has_context:
            return SymbolMatch(symbol=upper, candidates=[by_symbol[upper]])

    words = [t for t in re.findall(r"[a-z0-9]+", message.lower())]
    content = [w if w not in _STOP_NAME_WORDS else "" for w in words]
    for size in (3, 2, 1):
        for start in range(len(content) - size + 1):
            window = content[start : start + size]
            if any(not w for w in window):
                continue
            if size == 1 and len(window[0]) < 4:
                continue
            found = [
                entry
                for entry in master
                if _name_tokens(entry.get("name") or "")
                and _window_matches(window, _name_tokens(entry.get("name") or ""))
            ]
            if len(found) == 1:
                return SymbolMatch(symbol=found[0]["symbol"].upper(), candidates=found)
            if found:
                return SymbolMatch(symbol=None, candidates=found[:5])
    return SymbolMatch()


# ---------------------------------------------------------------------------- slots

_UNITS = {
    "k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "cr": 1e7, "crore": 1e7, "crores": 1e7,
}
_UNIT_PAT = r"(k|thousand|lakhs?|lacs?|crores?|cr)"
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_CURRENCY_BEFORE = re.compile(rf"(?:₹|rs\.?|inr)\s*{_NUM}\s*{_UNIT_PAT}?\b", re.IGNORECASE)
_CURRENCY_AFTER = re.compile(rf"{_NUM}\s*{_UNIT_PAT}?\s*(?:rupees?|rs\b|inr\b|₹)", re.IGNORECASE)
_UNIT_ONLY = re.compile(rf"\b{_NUM}\s*{_UNIT_PAT}\b", re.IGNORECASE)
_BARE_AMOUNT = re.compile(rf"(?<![\d.]){_NUM}(?![\d.])")
_NOT_AN_AMOUNT_AFTER = re.compile(
    r"\s*(?:-|to)?\s*\d*\s*(?:years?|yrs?|y\b|months?|stocks?|shares?|companies|names|picks|%|percent)",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}
_NUM_OR_WORD = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_COUNT_RANGE = re.compile(
    rf"{_NUM_OR_WORD}\s*(?:-|–|to)\s*{_NUM_OR_WORD}\s*(?:stocks?|shares?|companies|names|picks)",
    re.IGNORECASE,
)
_COUNT_SINGLE = re.compile(
    rf"{_NUM_OR_WORD}\s*(?:stocks?|shares?|companies|names|picks)", re.IGNORECASE
)
_COUNT_MAKE_IT = re.compile(rf"\b(?:make|change)\s+(?:it|that|this)\s+(?:to\s+)?{_NUM_OR_WORD}\b", re.IGNORECASE)
_YEARS = re.compile(r"(\d{1,2})\s*[- ]?\s*(?:years?|yrs?)\b", re.IGNORECASE)

_BEGINNER_RE = re.compile(
    r"\b(i\s*am|i'm|im)\s+(?:very\s+|totally\s+|completely\s+)?(?:new|a\s+beginner|beginner|a\s+newbie)"
    r"|\bnew\s+to\s+(?:the\s+)?(?:stock|invest|market|share|mutual|money)"
    r"|\bbeginners?\b|\bnewbie\b|\bjust\s+started\b|\bfirst\s+time\b|\bnever\s+invested\b"
    r"|\bno\s+experience\b|\bstarting\s+out\b|\bi\s+don'?t\s+know\s+(?:anything|much)\b",
    re.IGNORECASE,
)
_EXPERIENCED_RE = re.compile(
    r"\b(experienced|i\s+(?:have\s+been|am)\s+investing\s+for|seasoned|been\s+investing)\b", re.IGNORECASE
)
_SECTOR_HINTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("technology", re.compile(r"\b(tech|technology|software|it\s+(?:sector|stocks?|companies))\b", re.IGNORECASE)),
    ("financial", re.compile(r"\b(banking|banks|financials?|nbfc|insurance)\b", re.IGNORECASE)),
    ("health", re.compile(r"\b(pharma|pharmaceutical|healthcare|health\s+care)\b", re.IGNORECASE)),
    ("consumer", re.compile(r"\b(fmcg|consumer)\b", re.IGNORECASE)),
    ("energy", re.compile(r"\b(energy|oil|gas|power)\b", re.IGNORECASE)),
    ("auto", re.compile(r"\b(auto|automobile|automotive)\b", re.IGNORECASE)),
    ("materials", re.compile(r"\b(metals?|steel|cement|chemicals?)\b", re.IGNORECASE)),
    ("industrial", re.compile(r"\b(infra|infrastructure|industrials?|capital\s+goods)\b", re.IGNORECASE)),
)
_UNCERTAIN_PHRASES = (
    "don't know", "dont know", "not sure", "no idea", "unsure", "whatever", "you decide",
    "you choose", "no clue",
)


def is_uncertain(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _UNCERTAIN_PHRASES)


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _word_or_int(raw: str) -> int:
    return _NUMBER_WORDS.get(raw.lower()) or int(raw)


def _parse_amount(message: str, last_asked: str | None) -> float | None:
    for pattern in (_CURRENCY_BEFORE, _CURRENCY_AFTER, _UNIT_ONLY):
        match = pattern.search(message)
        if match:
            unit = match.group(2)
            value = _to_number(match.group(1)) * (_UNITS[unit.lower()] if unit else 1.0)
            if value > 0:
                return value
    asked = last_asked in ("amount", "monthly_amount")
    lowered = message.lower()
    investing = any(w in lowered for w in ("invest", "budget", "have", "save", "afford", "put"))
    if not asked and not investing:
        return None
    for match in _BARE_AMOUNT.finditer(message):
        if _NOT_AN_AMOUNT_AFTER.match(message, match.end()):
            continue
        value = _to_number(match.group(1))
        if value >= (1 if asked else 500):
            return value
    return None


def _parse_count(message: str) -> tuple[int | None, int | None]:
    match = _COUNT_RANGE.search(message)
    if match:
        low, high = sorted((_word_or_int(match.group(1)), _word_or_int(match.group(2))))
        return high, low
    match = _COUNT_SINGLE.search(message) or _COUNT_MAKE_IT.search(message)
    if match:
        count = _word_or_int(match.group(1))
        return count, count
    return None, None


def extract_slots(message: str, last_asked: str | None = None) -> Slots:
    """Deterministic slot filling. Every number is read from the user's own text."""
    text = message.lower().strip()
    uncertain = is_uncertain(text)
    values: dict[str, Any] = {}

    amount = _parse_amount(message, last_asked)
    if amount:
        values["amount_inr"] = amount
    if re.search(r"\b(per\s+month|a\s+month|monthly|every\s+month|each\s+month|/\s*month|sip)\b", text):
        values["amount_kind"] = "monthly"
    elif re.search(r"\b(lump\s*sum|one[- ]time|at\s+once|in\s+one\s+go|single\s+investment)\b", text):
        values["amount_kind"] = "lump_sum"

    count, count_min = _parse_count(message)
    if count:
        values["stock_count"] = min(count, 50)
        values["stock_count_min"] = min(count_min or count, 50)

    years = _YEARS.search(text)
    if years and int(years.group(1)) >= 1:
        values["horizon_years"] = int(years.group(1))
    elif last_asked == "horizon_years":
        bare = re.search(r"^\D*(\d{1,2})\D*$", text)
        if bare and int(bare.group(1)) >= 1:
            values["horizon_years"] = int(bare.group(1))
        elif uncertain:
            values["horizon_years"] = 5

    if re.search(r"\b(safe|safer|steady|low\s+risk|conservative|play\s+it\s+safe|less\s+risky|lower\s+risk)\b", text) or (
        last_asked == "risk_profile" and text in ("a", "1")
    ):
        values["risk_profile"] = "conservative"
    elif re.search(r"\b(aggressive|high\s+risk|higher\s+risk|riskier|big\s+swings|more\s+risky)\b", text) or (
        last_asked == "risk_profile" and text in ("c", "3")
    ):
        values["risk_profile"] = "aggressive"
    elif re.search(r"\b(balanced|moderate|medium\s+risk|flexi)\b", text) or (
        last_asked == "risk_profile" and text in ("b", "2")
    ) or last_asked == "risk_profile" and uncertain:
        values["risk_profile"] = "moderate"

    if _BEGINNER_RE.search(message):
        values["experience_level"] = "beginner"
    elif _EXPERIENCED_RE.search(message):
        values["experience_level"] = "intermediate"

    sectors = [name for name, pattern in _SECTOR_HINTS if pattern.search(message)]
    if sectors:
        values["sectors_wanted"] = sectors

    term = find_term(message)
    if term is not None:
        values["concept"] = term.term
    return Slots(**values)


# ---------------------------------------------------------------------------- intents

_FINANCE_RE = re.compile(
    r"\b(?:stock|share|mutual\s+fund|fund|sip|etf|invest\w*|nifty|sensex|market|portfolio|gold|debt|bond|"
    r"equit\w*|nav|dividend|return|nse|bse|ipo|rupee|saving|money|elss|demat|broker|price|buy|sell|"
    r"scheme|tax|ltcg|stcg|index|risk|amc|roe|p/e)s?\b|₹",
    re.IGNORECASE,
)
_OFF_TOPIC_RE = re.compile(
    r"\b(weather|cricket|football|soccer|movie|film|song|recipe|joke|politic\w*|election|celebrity|"
    r"girlfriend|boyfriend|homework|poem|translate|capital of|temperature|ipl|netflix|game score)\b",
    re.IGNORECASE,
)
_NEW_REQUEST_RE = re.compile(
    r"\b(suggest|recommend|give me|show me|list|portfolio|holdings|start over|reset|"
    r"market (?:today|now|overview)|how is the market)\b",
    re.IGNORECASE,
)
_FOLLOWUP_RE = re.compile(
    r"\b(make it|change it|make that|what about|instead|increase|decrease|safer|riskier|more|fewer|less|"
    r"another|different|only)\b",
    re.IGNORECASE,
)
_PLURAL_STOCKS_RE = re.compile(r"\b(stocks|shares|companies|equities)\b", re.IGNORECASE)
_LIST_VERBS_RE = re.compile(
    r"\b(suggest|recommend|give|list|best|top|some|which|what|name|pick|invest|buy|show|options|ideas)\b",
    re.IGNORECASE,
)
_MARKET_RE = re.compile(
    r"\b(how('?s| is) the (?:indian |stock |share )*market|market\s+(?:today|now|overview|mood|outlook|update|status|"
    r"condition|doing)|nifty|sensex|is it a good time to invest|is the market (?:up|down|high|low|crashing))\b",
    re.IGNORECASE,
)
_PORTFOLIO_RE = re.compile(
    r"\b(my\s+(?:portfolio|holdings|investments|demat)|portfolio\s+(?:risk|help|review|concentration|alerts)|"
    r"am i (?:too )?(?:concentrated|diversified))\b",
    re.IGNORECASE,
)
_RANKING_WORDS = ("name some", "name the", "list", "rank", "top ", "best funds", "decreasing order", "specific fund")
_START_RE = re.compile(
    r"\b(where\s+do\s+i\s+start|how\s+(?:do|can|should)\s+i\s+start|how\s+to\s+start|getting\s+started|"
    r"help\s+me\s+start|where\s+to\s+start)\b",
    re.IGNORECASE,
)


def _has_finance_word(text: str) -> bool:
    return _FINANCE_RE.search(text) is not None


def rule_intent(
    message: str,
    *,
    last_asked: str | None,
    has_prior_plan: bool,
    symbols: SymbolMatch,
    slots: Slots,
) -> Intent:
    """Deterministic classifier; the fallback when the model is down, and the reference the
    tests pin. Order matters: more specific requests are tested before broader ones."""
    t = message.lower().strip()
    words = t.split()
    defines = asks_for_definition(t)
    term = find_term(message)

    if last_asked and len(words) <= 6 and not defines and not _NEW_REQUEST_RE.search(t):
        return "answer"
    if _OFF_TOPIC_RE.search(t) and not _has_finance_word(t):
        return "off_topic"
    if (
        has_prior_plan
        and _FOLLOWUP_RE.search(t)
        and term is None
        and symbols.symbol is None
        and slots.provided()
    ):
        return "answer"
    if term is not None and (defines or is_bare_term(t)):
        return "education"
    if _START_RE.search(t) or (slots.experience_level == "beginner" and not _has_finance_word(t.replace("stock market", ""))):
        return "unclear"
    plural = _PLURAL_STOCKS_RE.search(t) is not None
    if (slots.stock_count or (plural and (slots.amount_inr or _LIST_VERBS_RE.search(t)))) and not (
        symbols.symbol and not plural
    ):
        return "stock_list"
    if _MARKET_RE.search(t):
        return "market_overview"
    if any(w in t for w in _RANKING_WORDS) and any(w in t for w in ("fund", "etf", "mutual")):
        return "fund_list"
    if _PORTFOLIO_RE.search(t):
        return "portfolio_help"
    if "etf" in t and "index fund" not in t and not defines:
        return "plan_sip_etf"
    if any(w in t for w in ("mutual fund", "sip", "monthly", "systematic", "index fund", "per month")):
        return "plan_sip_fund"
    if symbols.symbol or symbols.candidates or re.search(r"\b(stock|share|buy|sell)\b", t):
        return "stock_single"
    if defines and _has_finance_word(t):
        return "education"
    if _has_finance_word(t):
        return "unclear"
    return "unclear"


# ------------------------------------------------------------------------------ LLM

_LLM_PROMPT = """You label messages sent to an Indian investing assistant. Reply with ONE JSON object and nothing else.

{{"intent": <one of {intents}>, "slots": {{"amount_inr": number|null, "amount_kind": "lump_sum"|"monthly"|null, "horizon_years": integer|null, "risk_profile": "conservative"|"moderate"|"aggressive"|null, "stock_count": integer|null, "stock_count_min": integer|null, "symbol": string|null, "concept": string|null, "experience_level": "beginner"|"intermediate"|null, "sectors_wanted": [string]}}}}

Intent meanings:
education - asks what a finance term or concept means (ETF, SIP, P/E, NAV, ELSS, demat) or how the market works
stock_list - wants SEVERAL stocks suggested for an amount ("10 stocks for 10000 rupees")
stock_single - asks about ONE named stock
plan_sip_fund - wants a monthly mutual fund plan; plan_sip_etf - wants an ETF plan
fund_list - wants specific mutual funds named or ranked
market_overview - asks how the market is doing today
portfolio_help - asks about their own holdings
answer - a reply to the assistant's pending question (pending: {pending}) or a tweak of the previous plan (plan shown: {plan})
off_topic - not about investing; unclear - investing related but you cannot tell what they want

Use null for any slot the message does not state. Never guess a number. Message: {message}"""


def _parse_llm_json(raw: str) -> _LLMReply | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return _LLMReply.model_validate(json.loads(match.group(0)))
    except (ValueError, ValidationError):
        return None


async def _llm_extract(message: str, last_asked: str | None, has_prior_plan: bool) -> _LLMReply | None:
    try:
        model = get_llm("cheap")
        reply = await model.ainvoke(
            _LLM_PROMPT.format(
                intents=" | ".join(INTENTS),
                pending=last_asked or "none",
                plan=has_prior_plan,
                message=json.dumps(message),
            )
        )
        parsed = _parse_llm_json(extract_text(reply.content))
        if parsed is None:
            logger.info("Intent model returned unparseable output, using rules")
        return parsed
    except Exception as exc:
        logger.info("Intent model unavailable, using rules: %s", exc)
        return None


def _numbers_in(message: str) -> set[float]:
    return {float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*(?:\.\d+)?", message)}


def _merge_slots(rule: Slots, llm: Slots, message: str) -> Slots:
    """Rules win wherever they found a value. A model-supplied number is only kept when its
    digits actually appear in the user's text (no invented amounts); the symbol is never
    taken from the model here (see `extract`)."""
    merged = rule.model_copy(deep=True)
    seen = _numbers_in(message)
    expanded = {n * m for n in seen for m in (1, 1e3, 1e5, 1e7)}
    if merged.amount_inr is None and llm.amount_inr is not None and llm.amount_inr in expanded:
        merged.amount_inr = llm.amount_inr
    for name in ("horizon_years", "stock_count", "stock_count_min"):
        if getattr(merged, name) is None and getattr(llm, name) in seen:
            setattr(merged, name, getattr(llm, name))
    for name in ("amount_kind", "risk_profile", "experience_level", "concept"):
        if getattr(merged, name) is None and getattr(llm, name) is not None:
            setattr(merged, name, getattr(llm, name))
    if not merged.sectors_wanted and llm.sectors_wanted:
        merged.sectors_wanted = [s.lower() for s in llm.sectors_wanted][:3]
    return merged


async def extract(
    message: str,
    *,
    last_asked: str | None,
    has_prior_plan: bool,
    master: list[dict[str, str]],
) -> Extraction:
    """Intent + slots for one message. Never raises; always returns a valid `Extraction`."""
    slots = extract_slots(message, last_asked)
    symbols = resolve_symbols(message, master)
    rule = rule_intent(
        message, last_asked=last_asked, has_prior_plan=has_prior_plan, symbols=symbols, slots=slots
    )

    intent: Intent = rule
    source: Literal["llm", "rules"] = "rules"
    # A short reply to our own pending question is unambiguous: skip the model entirely.
    if rule != "answer":
        llm = await _llm_extract(message, last_asked, has_prior_plan)
        if llm is not None:
            source = "llm"
            slots = _merge_slots(slots, llm.slots, message)
            intent = llm.intent
            if intent == "answer" and not last_asked and not has_prior_plan:
                intent = rule
            if not symbols.symbol and not symbols.candidates and llm.slots.symbol:
                symbols = resolve_symbols(llm.slots.symbol, master)
            # Two guarded conflicts where the rules know better than the model: a request
            # for several stocks must never collapse into "which one company?", and a
            # clearly financial message must not be waved off as unclear/off-topic.
            if intent == "stock_single" and rule in ("stock_list", "education"):
                intent = rule
            if intent in ("unclear", "off_topic") and rule not in ("unclear", "answer", "off_topic"):
                intent = rule

    if symbols.symbol:
        slots.symbol = symbols.symbol
    return Extraction(
        intent=intent, slots=slots, symbol_candidates=symbols.candidates, source=source
    )
