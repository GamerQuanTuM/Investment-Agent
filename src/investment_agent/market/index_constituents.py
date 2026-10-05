"""Reviewed list of large, liquid NSE stocks used to build a candidate universe live when the
database has not been synced yet.

This is a *candidate list*, not a data source: every symbol is still confirmed against a live
quote before it can be picked (a delisted or renamed name simply returns no data and is
dropped), and every price and ratio comes from the market providers, never from this file.

Index membership changes at each NSE semi-annual review. Re-check against NSE's published
Nifty 50 and Nifty Next 50 lists and bump `LAST_REVIEWED` when you do.
"""

from __future__ import annotations

from datetime import date

LAST_REVIEWED = date(2026, 10, 1)

NIFTY_50: tuple[str, ...] = (
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR",
    "ICICIBANK", "INDUSINDBK", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN",
    "TRENT", "ULTRACEMCO", "WIPRO",
)

NIFTY_NEXT_50: tuple[str, ...] = (
    "ABB", "ADANIENSOL", "ADANIGREEN", "ADANIPOWER", "AMBUJACEM", "BAJAJHLDNG", "BANKBARODA",
    "BOSCHLTD", "BPCL", "BRITANNIA", "CANBK", "CGPOWER", "CHOLAFIN", "DABUR", "DIVISLAB", "DLF",
    "DMART", "GAIL", "GODREJCP", "HAVELLS", "HAL", "HINDZINC", "ICICIGI", "ICICIPRULI",
    "INDHOTEL", "INDIGO", "IOC", "IRCTC", "IRFC", "JINDALSTEL", "JSWENERGY", "LICI", "LODHA",
    "LTIM", "MAXHEALTH", "MOTHERSON", "NAUKRI", "PFC", "PIDILITIND", "PNB", "RECLTD", "SIEMENS",
    "SOLARINDS", "TATAPOWER", "TORNTPHARM", "TVSMOTOR", "UNITDSPR", "VBL", "VEDL", "ZYDUSLIFE",
)


def candidate_symbols() -> list[str]:
    """Nifty 50 first, then Nifty Next 50, without duplicates."""
    return list(dict.fromkeys((*NIFTY_50, *NIFTY_NEXT_50)))
