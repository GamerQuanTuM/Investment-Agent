"""Messages that need a careful, honest position rather than a plan:

- prediction: "which stock will double", "target price for TCS". Never forecast.
- guarantee: "is a SIP guaranteed to make money". Nothing in the market is guaranteed.
- emergency: money that may be needed soon (job loss, emergency savings, borrowed money).
- all_in: "put all my savings in one thing".

Detection is deterministic and runs before any model, so a model can neither miss nor soften
it. The *answer* is written by the model under the guardrails in `chat_ai` (Markdown, no
figures, no tickers, no forecasts, no buy/sell language); if the model is down or breaks a rule,
the reviewed fallback text below is used. Every reply ends with the not-registered-advice
disclaimer.

Sensitive kinds (emergency, all_in) are also human-in-the-loop: the chat first asks the user to
confirm they want general information (see `chat.py`), and only then answers.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from investment_agent.portfolio.stock_picker import DISCLAIMER
from investment_agent.research import chat_ai

GuardrailKind = Literal["emergency", "all_in", "guarantee", "prediction"]
SENSITIVE_KINDS: tuple[str, ...] = ("emergency", "all_in")

_EMERGENCY_RE = re.compile(
    r"\b(emergency\s+(?:fund|funds|savings|money|corpus|cash)|lost\s+my\s+job|laid\s+off|job\s+loss|"
    r"jobless|unemployed|(?:need|require)\s+(?:the\s+|this\s+)?money\s+(?:soon|shortly|next\s+\w+|in\s+(?:a\s+)?"
    r"(?:few|\d+)\s+\w+)|borrow(?:ed|ing)?\s+(?:money\s+)?to\s+invest|loan\s+to\s+invest|take\s+a\s+loan|"
    r"school\s+fees|medical\s+(?:bills?|emergency)|rent\s+money|retirement\s+(?:money|corpus|savings)|"
    r"child(?:ren)?'?s?\s+(?:education|school|college)\s+(?:money|fund|fees))\b",
    re.IGNORECASE,
)
_ALL_IN_RE = re.compile(
    r"\b(all\s+(?:of\s+)?my\s+(?:savings|money|corpus|salary)|(?:my\s+)?(?:entire|whole|life)\s+savings|"
    r"(?:invest|put|move|park)\s+everything|everything\s+i\s+have|all[- ]in)\b",
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

# Reviewed fallback text (Markdown), used only when the model is unavailable or breaks a rule.
_FALLBACKS: dict[str, tuple[str, list[str]]] = {
    "emergency": (
        ("I'm sorry you're dealing with that. When money may be needed soon, **keeping it safe matters more "
        "than growing it**, so *please don't put emergency savings into small caps*.\n\n"
        "- **Small-cap prices can swing sharply** and stay low for a long time.\n"
        "- You could be **forced to sell at a bad moment**, exactly when you need the cash.\n"
        "- A common approach is to keep emergency money somewhere **safe and easy to withdraw** (a savings "
        "account, a bank fixed deposit or a liquid fund) and to invest only money you won't need for several "
        "years.\n\n"
        "*That is general education, not a recommendation of a product, and no investment outcome can be "
        "promised.*"),
        ["What is risk vs return?", "What is diversification?", "What is an ETF?"],
    ),
    "all_in": (
        ("Putting **everything in one place** is the riskiest way to invest.\n\n"
        "- If that one thing falls, **all of your money falls with it**.\n"
        "- **Spreading money** across different companies and kinds of investment (diversification) means "
        "one bad outcome hurts far less.\n"
        "- Keep an **emergency cushion** outside investments, so you never have to sell in a downturn.\n\n"
        "*This is general education, not advice about what to buy.*"),
        ["What is diversification?", "What is risk vs return?", "What is an ETF?"],
    ),
    "guarantee": (
        ("**No.** Nothing in the stock market or in mutual funds is guaranteed, and that includes a SIP.\n\n"
        "- A **SIP** is only a way of investing a fixed amount regularly.\n"
        "- What you get back depends on the fund and the market, and you can *get back less than you put "
        "in*, especially over shorter periods.\n"
        "- *Past returns don't promise future ones*, and I can't promise any outcome.\n"
        "- What a SIP does help with is the **habit**: it spreads your buying over many months instead of "
        "one day."),
        ["What is a SIP?", "What is risk vs return?", "Plan a ₹5,000 monthly SIP"],
    ),
    "prediction": (
        ("**I can't predict prices**, and nobody honestly can: no one knows which stock will double or what "
        "a share will be worth later, so I don't give target prices, forecasts or promises.\n\n"
        "What I *can* show is what is measurable from the past:\n\n"
        "- **Business quality** (such as ROE and growth)\n"
        "- **How expensive** it is compared with its peers (P/E)\n"
        "- Its **recent price trend** and how **steady** it has been\n\n"
        "Each comes with a source and a date, and they describe the past, not the future."),
        ["Suggest 10 stocks for ₹10,000", "Should I buy TCS for 5 years?", "What is a P/E ratio?"],
    ),
}
_ADVISER_LINE = (
    "For decisions about your own money, a SEBI-registered adviser can look at your whole situation."
)


def detect(message: str) -> GuardrailKind | None:
    """Which guardrail applies, most protective first."""
    if _EMERGENCY_RE.search(message):
        return "emergency"
    if _ALL_IN_RE.search(message):
        return "all_in"
    if _GUARANTEE_RE.search(message):
        return "guarantee"
    if _PREDICTION_RE.search(message):
        return "prediction"
    return None


def sensitive(message: str) -> GuardrailKind | None:
    """The sensitive kind (needs the user's confirmation first), else None."""
    kind = detect(message)
    return kind if kind in SENSITIVE_KINDS else None


async def reply(message: str, kind: str | None = None) -> dict[str, Any]:
    """The answer for a guardrail message: model-written under `chat_ai`'s checks, else the
    reviewed fallback. Always ends with the disclaimer."""
    kind = kind or detect(message) or "prediction"
    fallback_text, chips = _FALLBACKS[kind]
    written = await chat_ai.write(chat_ai.TASKS[kind], message, reference=fallback_text)
    body = written or fallback_text
    tail = f"{_ADVISER_LINE}\n\n" if kind in SENSITIVE_KINDS else ""
    return {
        "text": f"{body}\n\n{tail}*{DISCLAIMER}*",
        "suggestions": list(chips),
        "kind": kind,
        "answered_by": "ai" if written else "reviewed",
    }
