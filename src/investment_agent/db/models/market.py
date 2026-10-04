from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from investment_agent.db.models.base import Base, TimestampMixin


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "security_id", name="uq_instrument_exchange_security"),
    )

    exchange: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    segment: Mapped[str] = mapped_column(String(20), nullable=False, default="E")
    security_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trading_symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    instrument_name: Mapped[str] = mapped_column(String(32), nullable=False, default="EQUITY")


class DailyBar(Base, TimestampMixin):
    __tablename__ = "daily_bars"
    __table_args__ = (
        UniqueConstraint("security_id", "bar_time", name="uq_daily_bar_security_time"),
    )

    security_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scrip_code: Mapped[str] = mapped_column(String(40), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class FundamentalSnapshot(Base, TimestampMixin):
    """Sourced fundamental facts. Prices are not stored here."""

    __tablename__ = "fundamental_snapshots"

    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    security_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sector: Mapped[str] = mapped_column(String(100), nullable=False, default="Unclassified")
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, default="stock")
    data_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    roe_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    roce_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_to_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    promoter_pledge_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth_3y_cagr_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_growth_3y_cagr_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_value_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="Company Filing")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class NavRecord(Base, TimestampMixin):
    __tablename__ = "nav_records"
    __table_args__ = (UniqueConstraint("scheme_code", "nav_date", name="uq_nav_scheme_date"),)

    scheme_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    scheme_name: Mapped[str] = mapped_column(String(400), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nav: Mapped[float] = mapped_column(Float, nullable=False)
    nav_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)


class EvidenceRecord(Base, TimestampMixin):
    __tablename__ = "evidence_records"

    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    claim: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
