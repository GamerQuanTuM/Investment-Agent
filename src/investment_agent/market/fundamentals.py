"""Persist sourced fundamental facts. INDstocks does not provide these ratios."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from investment_agent.db.models.base import utc_now
from investment_agent.db.models.market import EvidenceRecord, FundamentalSnapshot
from investment_agent.db.session import async_session_factory


async def store_fundamental_snapshots(rows: list[dict[str, Any]]) -> int:
    now = utc_now()
    async with async_session_factory() as session:
        for row in rows:
            data_date = row["data_date"]
            if isinstance(data_date, str):
                data_date = datetime.fromisoformat(data_date)
            symbol = str(row["symbol"]).upper()
            session.add(
                FundamentalSnapshot(
                    symbol=symbol,
                    security_id=row.get("security_id"),
                    name=row.get("name") or symbol,
                    sector=row.get("sector") or "Unclassified",
                    asset_type=row.get("asset_type") or "stock",
                    data_date=data_date,
                    roe_pct=row.get("roe_pct"),
                    roce_pct=row.get("roce_pct"),
                    debt_to_equity=row.get("debt_to_equity"),
                    promoter_pledge_pct=row.get("promoter_pledge_pct"),
                    revenue_growth_3y_cagr_pct=row.get("revenue_growth_3y_cagr_pct"),
                    profit_growth_3y_cagr_pct=row.get("profit_growth_3y_cagr_pct"),
                    eps=row.get("eps"),
                    book_value_per_share=row.get("book_value_per_share"),
                    market_cap_cr=row.get("market_cap_cr"),
                    source_name=row["source_name"],
                    source_url=row["source_url"],
                    source_type=row.get("source_type") or "Company Filing",
                    raw_payload=row,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                EvidenceRecord(
                    symbol=symbol,
                    claim=(
                        f"{symbol} fundamentals as of {data_date.isoformat()} "
                        f"from {row['source_name']}"
                    ),
                    source_name=row["source_name"],
                    source_url=row["source_url"],
                    source_type=row.get("source_type") or "Company Filing",
                    data_date=data_date,
                    retrieved_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
    return len(rows)
