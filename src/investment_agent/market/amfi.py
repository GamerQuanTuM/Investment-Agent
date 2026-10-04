"""Official AMFI daily NAV file. No API key.

NAVAll.txt groups scheme rows under two kinds of non-scheme lines with no semicolons:
a fund house name (e.g. "Aditya Birla Sun Life Mutual Fund"), followed by one or more
category header lines (e.g. "Open Ended Schemes(Equity Scheme - Large Cap Fund)"), each
followed by that category's scheme rows. `parse_nav_file` tracks both as it scans so every
scheme row carries its fund house and category (Workstream B, B1) — previously these
header lines were skipped entirely and that context was lost.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")

_AMFI_COLUMN_HEADER = "scheme code"


def _looks_like_category_header(line: str) -> bool:
    """AMFI category headers always name a scheme kind in parentheses, e.g.
    "Open Ended Schemes(Equity Scheme - Large Cap Fund)" or "Close Ended Schemes(...)"."""
    lowered = line.lower()
    return "schemes(" in lowered or "scheme(" in lowered


def classify_plan(scheme_name: str) -> str:
    """Direct vs Regular, from the scheme name text. Deterministic, never guessed."""
    return "direct" if "direct" in scheme_name.lower() else "regular"


def classify_option(scheme_name: str) -> str:
    """Growth vs IDCW (dividend), from the scheme name text.

    AMFI scheme names almost always say one or the other explicitly; Growth is the safe
    default on the rare row that names neither, since it's the overwhelmingly common case
    for schemes that don't mention a payout option at all.
    """
    lowered = scheme_name.lower()
    if "idcw" in lowered or "dividend" in lowered:
        return "idcw"
    return "growth"


def classify_sebi_group(category: str | None, scheme_name: str) -> str:
    """Large/mid/small/flexi/elss/index/debt/hybrid/gold/other, from category + name text.

    Order matters: more specific groups (ELSS, gold, index) are checked before the broader
    cap-based and debt/hybrid buckets, and gold/silver is checked *before* the generic
    "index"/"etf" catch-all so a Gold ETF isn't misclassified as an equity index tracker
    just because its name also contains "ETF".
    """
    text = f"{category or ''} {scheme_name}".lower()
    if any(word in text for word in (
        "elss",
        "tax saving",
        "tax saver",
        "taxsaver",
        "tax plan",
        "taxshield",
        "tax gain",
        "taxgain",
    )):
        return "elss"
    # Checked before the generic "etf" catch-all below: a Gold/Silver ETF is a commodity
    # fund, not an equity index tracker, even though its name also contains "ETF".
    # Word boundaries so "Goldman" is not read as a gold fund.
    if re.search(r"\bgold\b", text) or re.search(r"\bsilver\b", text):
        return "gold"
    if any(word in text for word in ("index", "etf", "nifty", "sensex", "equal weight", "nasdaq")):
        return "index"
    if "large & mid" in text or "large and mid" in text:
        return "large_mid"
    if "large cap" in text or "largecap" in text or "bluechip" in text or "blue chip" in text:
        return "large"
    if "mid cap" in text or "midcap" in text:
        return "mid"
    if "small cap" in text or "smallcap" in text:
        return "small"
    if "flexi cap" in text or "flexicap" in text or "multi cap" in text or "multicap" in text:
        return "flexi"
    if any(word in text for word in (
        "hybrid",
        "balanced",
        "arbitrage",
        "equity savings",
        "multi asset",
        "asset allocation",
        "monthly income",
    )):
        return "hybrid"
    if "debt scheme" in text or any(word in text for word in (
        "debt",
        "liquid",
        "overnight",
        "gilt",
        "bond",
        "money market",
        "short term",
        "short duration",
        "ultra short",
        "low duration",
        "medium term",
        "medium to long",
        "fmp",
        "credit risk",
        "corporate bond",
        "income fund",
        "cash plus",
        "deposit fund",
        "floater",
        "treasury",
        "dynamic bond",
        "banking and psu",
        "g-sec",
        "gsec",
        "govt.sec",
        "govt sec",
        "government securities",
        "accrual",
        "triple ace",
    )):
        return "debt"
    if any(word in text for word in (
        "equity scheme",
        "equity",
        "opportunities",
        "mnc",
        "fmcg",
        "pharma",
        "technology",
        "value fund",
        "ethical",
        "diversified",
        "growth fund",
    )) or " tech" in f" {text} ":
        return "equity"
    if any(word in text for word in ("retirement", "children", "child benefit", "ulis")):
        return "solution"
    return "other"


def category_index(text: str) -> dict[str, str]:
    """Map scheme code to the AMFI category header above that row."""
    index: dict[str, str] = {}
    category: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6 or not parts[0].isdigit():
            if stripped.lower().startswith(_AMFI_COLUMN_HEADER):
                continue
            if _looks_like_category_header(stripped):
                category = stripped
            else:
                category = None
            continue
        if category:
            index[parts[0]] = category
    return index


def parse_nav_file(text: str, scheme_codes: set[str] | None = None) -> list[dict[str, object]]:
    """Parse NAVAll.txt into scheme rows, each carrying its fund house and category."""
    rows: list[dict[str, object]] = []
    wanted = {code.strip() for code in scheme_codes} if scheme_codes else None
    fund_house: str | None = None
    category: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6 or not parts[0].isdigit():
            if stripped.lower().startswith(_AMFI_COLUMN_HEADER):
                continue
            if _looks_like_category_header(stripped):
                category = stripped
            else:
                fund_house = stripped
                category = None
            continue

        scheme_code = parts[0]
        if wanted is not None and scheme_code not in wanted:
            continue
        nav_raw = parts[4]
        if not nav_raw or nav_raw.upper() in {"N.A.", "NA", "-"}:
            continue
        try:
            nav = float(nav_raw)
            nav_date = datetime.strptime(parts[5], "%d-%b-%Y").replace(tzinfo=IST)
        except ValueError:
            continue
        isin = parts[2] or parts[1] or None
        scheme_name = parts[3]
        rows.append(
            {
                "scheme_code": scheme_code,
                "scheme_name": scheme_name,
                "isin": isin,
                "nav": nav,
                "nav_date": nav_date,
                "fund_house": fund_house,
                "category": category,
                "plan": classify_plan(scheme_name),
                "option": classify_option(scheme_name),
                "sebi_group": classify_sebi_group(category, scheme_name),
            }
        )
    return rows


async def fetch_nav_file(url: str, http: httpx.AsyncClient | None = None) -> str:
    if http is not None:
        response = await http.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
