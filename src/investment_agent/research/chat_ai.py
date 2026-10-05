"""AI-written explanations, comparisons and safety replies, under guardrails.

The model decides how to explain; the code decides what it may say:

- It is given the reviewed glossary / comparison facts as *reference* and told to stay
  consistent with them, but to write in its own words for the person's actual question.
- It writes Markdown (bullets, bold, italics, tables) which the chat UI renders as rich text.
- Its output is checked mechanically before anyone sees it (`passes_ai_check`): no currency
  amounts, percentages, tickers, forecasts, promises or buy/sell instructions. A reply that
  fails the check, times out or errors is discarded and the caller uses the reviewed text,
  so a model outage never blocks an answer and a model slip never reaches the user.

Numbers that matter (plans, stock lists, funds) are never written here: Python computes them.
"""

from __future__ import annotations

import asyncio
import logging
import re

from investment_agent.llm.factory import extract_text, get_llm

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 40.0  # the model thinks for 10-20 s on a real answer
MAX_CHARS = 3000

STYLE_RULES = (
    "You are a warm, careful guide to Indian investing for people who have never invested. "
    "Write ONLY in Markdown: start with a one- or two-sentence plain-English answer, then use short "
    "bullet points; put **bold** on key terms and *italics* on caveats; when comparing things use a "
    "Markdown table with the aspects as rows and the things compared as columns, followed by a "
    "bullet starting with **Bottom line:**. Use at most one ### heading. No emojis. Keep it under "
    "about 200 words and explain any jargon you use.\n"
    "HARD RULES: You must NOT mention any price, index level, percentage, return, fee amount, tax "
    "rate or rupee amount for a real security or fund. You must NOT name any company, fund or "
    "ticker. You must NOT predict or promise any outcome, say 'guaranteed', or tell the person to "
    "buy, sell or hold anything. This is education, not personal or SEBI-registered advice. If the "
    "question is not about how investing or markets work, say you can only explain investing."
)

# Upper-case words that are acronyms for concepts, not company tickers.
ALLOWED_ACRONYMS = frozenset(
    {
        "ETF", "ETFS", "SIP", "STP", "SWP", "NAV", "IPO", "NSE", "BSE", "SEBI", "RBI", "ELSS", "PE", "ROE",
        "ROCE", "GDP", "EMI", "KYC", "PAN", "AMC", "FD", "RD", "IDCW", "TER", "LTCG", "STCG", "AUM",
        "CAGR", "UPI", "DEMAT", "MF", "EPS", "DP", "AI", "NFO", "PPF", "NPS", "EPF", "GST", "INR", "I", "A",
    }
)  # fmt: skip

_CURRENCY = re.compile(r"[₹$€£]|\b(?:rs\.?|inr)\s*\d|\d\s*(?:rupees?|crores?|lakhs?|lacs?)\b", re.IGNORECASE)
_PERCENT = re.compile(r"%|\bpercent(?:age)?\b", re.IGNORECASE)
# Affirmative promises only: a reply may say "nothing is guaranteed" or "I don't give target
# prices" (that is the point of the guardrail replies) but may not make such a claim itself.
_PROMISE = re.compile(
    r"\b(you should (?:buy|sell|hold|invest|put)|i recommend|i suggest you|(?:is|are|will be)\s+guaranteed\s+to|"
    r"will (?:earn|return|grow|rise|double|triple|go up|outperform|beat)|sure[- ]?shot|can'?t lose|"
    r"buy now|sell now|multibagger|is certain to)\b",
    re.IGNORECASE,
)


# "No one knows which stock will double" and "I can't say whether it will rise" are denials, not
# forecasts: a "will ..." claim is ignored when the words before it deny, question or hedge it.
_DENIAL_CONTEXT = re.compile(
    r"\b(which|whether|if|know|knows|predict|cannot|can't|can not|nobody|no one|never|not|won't|unless)\b",
    re.IGNORECASE,
)


def _has_promise(text: str) -> bool:
    for match in _PROMISE.finditer(text):
        if match.group(0).lower().startswith("will "):
            before = text[max(0, match.start() - 60) : match.start()]
            if _DENIAL_CONTEXT.search(before):
                continue
        return True
    return False


def passes_ai_check(text: str) -> bool:
    """True only if a model-written answer contains no figures, tickers, forecasts or advice."""
    if not text.strip() or len(text) > MAX_CHARS:
        return False
    if _CURRENCY.search(text) or _PERCENT.search(text) or _has_promise(text):
        return False
    return all(word in ALLOWED_ACRONYMS for word in re.findall(r"\b[A-Z]{2,}\b", text))


def _clean(text: str) -> str:
    text = text.strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", text, re.DOTALL)
    return fenced.group(1).strip() if fenced else text


async def write(task: str, question: str, reference: str = "") -> str | None:
    """One guarded model answer in Markdown, or None (caller falls back to reviewed text)."""
    prompt = f"{STYLE_RULES}\n\nTASK: {task}\n"
    if reference:
        prompt += (
            "\nREVIEWED REFERENCE (stay consistent with it; reword it for this person's question "
            f"and explain more simply, but add no figures):\n{reference}\n"
        )
    prompt += f"\nUSER QUESTION: {question}"
    try:
        model = get_llm("cheap")
        reply = await asyncio.wait_for(model.ainvoke(prompt), timeout=LLM_TIMEOUT_SECONDS)
        text = _clean(extract_text(reply.content))
    except Exception as exc:
        logger.info("AI answer unavailable, using reviewed text: %s", exc)
        return None
    if not passes_ai_check(text):
        logger.info("AI answer rejected by the guardrail check, using reviewed text")
        return None
    return text


TASKS = {
    "explain": "Explain this one investing concept to the person, answering their actual question.",
    "compare": (
        "Compare the two (or three) things the person asks about. Use a table with these rows: how you "
        "buy, whether a demat account is needed, minimum amount, costs, who it suits, main risk; then a "
        "**Bottom line:** bullet saying which is simpler for a beginner and why."
    ),
    "prediction": (
        "The person is asking for a price prediction or target price. Politely decline: nobody can "
        "predict prices. Explain in bullets what you CAN show (a company's past business quality, how "
        "expensive it is versus peers, its recent price trend, how steady it has been, each with a "
        "source and date) and invite them to ask for that."
    ),
    "guarantee": (
        "The person asks whether an investment is guaranteed or risk-free. Answer honestly: nothing in "
        "the market is guaranteed, values rise and fall and can end below what was put in, past results "
        "do not promise the future. Mention what the thing does help with, in bullets."
    ),
    "emergency": (
        "The person may be about to risk money they might need soon (emergency savings, job loss, "
        "borrowed money, money for rent, fees or medical needs). Be kind. Say plainly that money needed "
        "soon should be kept safe and easy to withdraw rather than put in volatile investments, explain "
        "briefly why in bullets, and mention safe places in general terms. Do not recommend a product."
    ),
    "all_in": (
        "The person wants to put all or most of their money into one thing. Explain concentration risk "
        "in bullets: why spreading money across different investments, and keeping an emergency "
        "cushion, matters. Do not tell them what to buy."
    ),
}
