"""Official AMFI daily NAV file. No API key."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")


def parse_nav_file(text: str, scheme_codes: set[str] | None = None) -> list[dict[str, object]]:
    """Parse NAVAll.txt. Category header lines have no semicolon-separated NAV."""
    rows: list[dict[str, object]] = []
    wanted = {code.strip() for code in scheme_codes} if scheme_codes else None
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6 or not parts[0].isdigit():
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
        rows.append(
            {
                "scheme_code": scheme_code,
                "scheme_name": parts[3],
                "isin": isin,
                "nav": nav,
                "nav_date": nav_date,
            }
        )
    return rows


async def fetch_nav_file(url: str, http: httpx.AsyncClient | None = None) -> str:
    if http is not None:
        response = await http.get(url)
        response.raise_for_status()
        return response.text
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
