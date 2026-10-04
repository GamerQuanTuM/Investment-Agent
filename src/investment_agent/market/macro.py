"""FRED's public CSV export — free, keyless macro data, used for the F3 "Market Mood"
signal. Verified live from this environment (confirmed via a direct curl during
development, same convention as `market/mfapi.py`/`market/news.py`): `fredgraph.csv?id=<series>`
needs no API key, unlike FRED's JSON API.

Two India series are used, both chosen for actually being live/current enough to be
useful, not just "an India series that exists" — several candidates checked during
development (e.g. `INTDSRINM193N`, RBI's discount rate) were stale by years and were
deliberately left out rather than shown as if they were current:

* `DEXINUS` — Indian Rupees to U.S. Dollar spot exchange rate. Updated daily.
* `CPALTT01INM659N` — India CPI, **"Growth rate same period previous year"** (confirmed
  from FRED's own series description page, not assumed from the series ID) — i.e. this
  series IS already the YoY inflation rate, computed upstream by FRED/OECD from the raw
  index. An earlier draft of this module wrongly assumed it was a raw index level and
  tried to re-derive YoY % in Python from two readings 12 months apart; the actual values
  (~2-5, matching realistic India CPI inflation) are nowhere near an index level (~150-160,
  which is what the *separate* `INDCPIALLMINMEI` series returns) — caught before shipping
  by checking the live values against the series' own FRED page rather than trusting the
  series-ID naming convention. Fixed by using the value as the rate directly. Updated
  monthly, with a real reporting lag (observed ~12-18 months stale even for official
  data) — `data_date` is always returned alongside the value so a caller/UI can show how
  current it actually is, never hide the lag.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

import httpx

from investment_agent.market.cache import CacheTTL, cache_get, cache_set

logger = logging.getLogger(__name__)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)

USD_INR_SERIES_ID = "DEXINUS"
CPI_INDIA_SERIES_ID = "CPALTT01INM659N"


async def _fetch_series(series_id: str) -> list[dict[str, Any]] | None:
    """Chronological (oldest-first, matching FRED's own CSV order) list of
    `{"date": "YYYY-MM-DD", "value": float}`. Rows with a missing value (FRED uses `.`)
    are dropped. `None` (never raises) on any network/parse failure."""
    cache_key = f"fred:{series_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(FRED_CSV_URL, params={"id": series_id})
    except httpx.HTTPError as exc:
        logger.info("FRED series %s failed: %s", series_id, exc)
        return None
    if response.status_code >= 400:
        return None

    rows: list[dict[str, Any]] = []
    reader = csv.reader(io.StringIO(response.text))
    header = next(reader, None)
    if not header or len(header) < 2:
        return None
    for row in reader:
        if len(row) < 2:
            continue
        raw_date, raw_value = row[0], row[1]
        if raw_value in ("", ".", "NA"):
            continue
        try:
            rows.append({"date": raw_date, "value": float(raw_value)})
        except ValueError:
            continue

    if not rows:
        return None

    await cache_set(cache_key, json.dumps(rows), CacheTTL.MACRO)
    return rows


async def usd_inr_rate() -> dict[str, Any] | None:
    """Latest USD/INR spot rate. `None` (DATA_UNAVAILABLE) if FRED can't be reached."""
    series = await _fetch_series(USD_INR_SERIES_ID)
    if not series:
        return None
    latest = series[-1]
    return {
        "value": latest["value"],
        "data_date": latest["date"],
        "source_name": "FRED (St. Louis Fed) — DEXINUS",
        "source_url": f"https://fred.stlouisfed.org/series/{USD_INR_SERIES_ID}",
    }


async def cpi_inflation_yoy() -> dict[str, Any] | None:
    """Latest YoY CPI inflation % for India. `CPALTT01INM659N` is already a
    "growth rate same period previous year" series (confirmed on FRED's own series page,
    see module docstring) — this reads its latest value directly rather than re-deriving
    YoY from an index level. `None` if FRED can't be reached."""
    series = await _fetch_series(CPI_INDIA_SERIES_ID)
    if not series:
        return None

    latest = series[-1]
    return {
        "value_pct": round(latest["value"], 2),
        "data_date": latest["date"],
        "source_name": "FRED (St. Louis Fed) — CPALTT01INM659N",
        "source_url": f"https://fred.stlouisfed.org/series/{CPI_INDIA_SERIES_ID}",
    }


async def get_macro_snapshot() -> dict[str, Any]:
    """Convenience aggregator for the F3 "Market Mood" strip. Each field degrades to its
    own `DATA_UNAVAILABLE` independently rather than failing the whole snapshot."""
    usd_inr = await usd_inr_rate()
    cpi = await cpi_inflation_yoy()
    return {
        "usd_inr": {"status": "OK", **usd_inr} if usd_inr is not None else {"status": "DATA_UNAVAILABLE"},
        "cpi_inflation_yoy": {"status": "OK", **cpi} if cpi is not None else {"status": "DATA_UNAVAILABLE"},
    }
