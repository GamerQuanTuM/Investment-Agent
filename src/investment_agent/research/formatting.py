"""One way to write money and percentages in chat text: ₹20,000, ₹1,00,000, 12.5%.

Indian digit grouping (last three digits, then pairs), no ".0" on whole amounts, never "INR"
or "Rs". Used by every chat reply, including text a model wrote (`normalize_money_text`).
"""

from __future__ import annotations

import re

_RUPEE_TEXT = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*(\d(?:[\d,]*\d)?(?:\.\d+)?)(?:\s*(?:/-|rupees?))?",
    re.IGNORECASE,
)


def _group_indian(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join([*pairs, tail])


def inr(value: float | None) -> str:
    """₹20,000 (whole rupees) or ₹318.55 (when paise matter). "—" when there is no value."""
    if value is None:
        return "—"
    number = round(float(value), 2)
    sign = "-" if number < 0 else ""
    number = abs(number)
    whole, _, frac = f"{number:.2f}".partition(".")
    text = _group_indian(whole)
    if frac != "00":
        text += f".{frac}"
    return f"{sign}₹{text}"


def pct(value: float | None, decimals: int = 1) -> str:
    """12.5% / 40% (one decimal at most, no trailing ".0"). "—" when there is no value."""
    if value is None:
        return "—"
    text = f"{float(value):.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}%"


def normalize_money_text(text: str) -> str:
    """Rewrite any "₹20000.0", "Rs. 20,000" or "INR 20000" in free text into `inr()` form."""

    def repl(match: re.Match[str]) -> str:
        return inr(float(match.group(1).replace(",", "")))

    return _RUPEE_TEXT.sub(repl, text)
