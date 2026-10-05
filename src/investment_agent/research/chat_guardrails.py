"""Messages the assistant must answer with a fixed, honest position rather than a plan:

- prediction: "which stock will double", "target price for TCS". It never forecasts.
- guarantee: "is a SIP guaranteed to make money". Nothing in the market is guaranteed.
- emergency: money that may be needed soon (job loss, emergency savings, borrowed money).

The replies are fixed text reviewed like the glossary: no figures, no tickers, no buy language.
Detection is deterministic and runs before any model, so a model can neither miss nor soften it.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from investment_agent.portfolio.stock_picker import DISCLAIMER

GuardrailKind = Literal["emergency", "guarantee", "prediction"]

_EMERGENCY_RE = re.compile(
    r"\b(emergency\s+(?:fund|funds|savings|money|corpus|cash)|lost\s+my\s+job|laid\s+off|job\s+loss|"
    r"jobless|unemployed|(?:need|require)\s+(?:the\s+|this\s+)?money\s+(?:soon|shortly|next\s+\w+|in\s+(?:a\s+)?"
    r"(?:few|\d+)\s+\w+)|borrow(?:ed|ing)?\s+(?:money\s+)?to\s+invest|loan\s+to\s+invest|take\s+a\s+loan|"
    r"school\s+fees|medical\s+(?:bills?|emergency)|rent\s+money)\b",
    re.IGNORECASE,
)
_GUARANTEE_RE = re.compile(
    r"\b(guarantee[ds]?|risk[- ]?free|assured\s+returns?|100\s*%\s+safe|no\s+risk|safe\s+to\s+invest|"
    r"can\s+i\s+lose\s+(?:all\s+)?(?:my\s+)?money|will\s+i\s+lose\s+(?:my\s+)?money|sure[- ]?shot)\b",
    re.IGNORECASE,
)
_PREDICTION_RE = re.compile(
    r"\b(target\s+price|price\s+target|multibagger|jackpot|get\s+rich\s+quick|predict(?:ion|ions)?|forecast|"
    r"will\s+(?:\w+\s+){0,3}(?:double|triple|multiply|go\s+up|go\s+down|rise|moon|crash|fall|reach|hit|beat)|"
    r"(?:double|triple|multiply)\s+(?:my\s+money|in\s+\d+)|best\s+stock\s+to\s+(?:double|multiply))\b",
    re.IGNORECASE,
)

_REPLIES: dict[str, tuple[str, list[str]]] = {
    "emergency": (
        ("I'm sorry you're dealing with that. When money may be needed soon, keeping it safe matters "
        "more than growing it, so please don't put emergency savings into small caps. Small-cap "
        "prices can swing sharply and stay low for a long time, and you could be forced to sell at "
        "a bad moment, exactly when you need the cash.\n\n"
        "A common approach is to keep emergency money somewhere safe and easy to withdraw (a "
        "savings account, a bank fixed deposit or a liquid fund) and to invest only money you won't "
        "need for several years. That is general education, not a recommendation of a product, and "
        "no investment outcome can be promised."),
        ["What is risk vs return?", "What is diversification?", "What is an ETF?"],
    ),
    "guarantee": (
        ("No. Nothing in the stock market or in mutual funds is guaranteed, and that includes a SIP. "
        "A SIP is only a way of investing a fixed amount regularly; what you get back depends on the "
        "fund and the market, and you can get back less than you put in, especially over shorter "
        "periods. Past returns don't promise future ones, and I can't promise any outcome.\n\n"
        "What a SIP does help with is the habit: it spreads your buying over many months instead of "
        "one day, so you don't have to guess the best moment."),
        ["What is a SIP?", "What is risk vs return?", "Plan a ₹5,000 monthly SIP"],
    ),
    "prediction": (
        ("I can't predict prices, and nobody honestly can: no one knows which stock will double or "
        "what a share will be worth later, so I don't give target prices, forecasts or promises.\n\n"
        "What I can show is what is measurable from the past: a company's business quality (such "
        "as ROE and growth), how expensive it is compared with its peers (P/E), its recent price "
        "trend and how steady it has been, each with a source and a date. Those describe the past, "
        "not the future."),
        ["Suggest 10 stocks for ₹10,000", "Should I buy TCS for 5 years?", "What is a P/E ratio?"],
    ),
}


def detect(message: str) -> GuardrailKind | None:
    """Which guardrail applies, most protective first: emergency money, then guarantees, then
    predictions."""
    if _EMERGENCY_RE.search(message):
        return "emergency"
    if _GUARANTEE_RE.search(message):
        return "guarantee"
    if _PREDICTION_RE.search(message):
        return "prediction"
    return None


def reply(message: str) -> dict[str, Any]:
    kind = detect(message) or "prediction"
    text, chips = _REPLIES[kind]
    return {"text": f"{text}\n\n{DISCLAIMER}", "suggestions": list(chips), "kind": kind}
