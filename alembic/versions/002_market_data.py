"""Market data tables and holding identifiers

Revision ID: 002_market_data
Revises: 001_initial_schema
Create Date: 2026-10-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_market_data"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("holdings", sa.Column("security_id", sa.String(length=32), nullable=True))
    op.add_column("holdings", sa.Column("isin", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_holdings_security_id"), "holdings", ["security_id"], unique=False)

    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("exchange", sa.String(length=10), nullable=False),
        sa.Column("segment", sa.String(length=20), nullable=False),
        sa.Column("security_id", sa.String(length=32), nullable=False),
        sa.Column("trading_symbol", sa.String(length=64), nullable=False),
        sa.Column("symbol_name", sa.String(length=64), nullable=False),
        sa.Column("series", sa.String(length=16), nullable=False),
        sa.Column("instrument_name", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange", "security_id", name="uq_instrument_exchange_security"),
    )
    op.create_index(op.f("ix_instruments_exchange"), "instruments", ["exchange"], unique=False)
    op.create_index(op.f("ix_instruments_security_id"), "instruments", ["security_id"], unique=False)
    op.create_index(op.f("ix_instruments_symbol_name"), "instruments", ["symbol_name"], unique=False)
    op.create_index(op.f("ix_instruments_trading_symbol"), "instruments", ["trading_symbol"], unique=False)

    op.create_table(
        "daily_bars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("security_id", sa.String(length=32), nullable=False),
        sa.Column("scrip_code", sa.String(length=40), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("bar_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("security_id", "bar_time", name="uq_daily_bar_security_time"),
    )
    op.create_index(op.f("ix_daily_bars_security_id"), "daily_bars", ["security_id"], unique=False)
    op.create_index(op.f("ix_daily_bars_symbol"), "daily_bars", ["symbol"], unique=False)

    op.create_table(
        "fundamental_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("data_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("roe_pct", sa.Float(), nullable=True),
        sa.Column("roce_pct", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("promoter_pledge_pct", sa.Float(), nullable=True),
        sa.Column("revenue_growth_3y_cagr_pct", sa.Float(), nullable=True),
        sa.Column("profit_growth_3y_cagr_pct", sa.Float(), nullable=True),
        sa.Column("eps", sa.Float(), nullable=True),
        sa.Column("book_value_per_share", sa.Float(), nullable=True),
        sa.Column("market_cap_cr", sa.Float(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fundamental_snapshots_symbol"), "fundamental_snapshots", ["symbol"], unique=False)
    op.create_index(
        op.f("ix_fundamental_snapshots_security_id"),
        "fundamental_snapshots",
        ["security_id"],
        unique=False,
    )

    op.create_table(
        "nav_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scheme_code", sa.String(length=20), nullable=False),
        sa.Column("scheme_name", sa.String(length=400), nullable=False),
        sa.Column("isin", sa.String(length=20), nullable=True),
        sa.Column("nav", sa.Float(), nullable=False),
        sa.Column("nav_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme_code", "nav_date", name="uq_nav_scheme_date"),
    )
    op.create_index(op.f("ix_nav_records_scheme_code"), "nav_records", ["scheme_code"], unique=False)

    op.create_table(
        "evidence_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("claim", sa.String(length=2000), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("data_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_records_symbol"), "evidence_records", ["symbol"], unique=False)


def downgrade() -> None:
    op.drop_table("evidence_records")
    op.drop_table("nav_records")
    op.drop_table("fundamental_snapshots")
    op.drop_table("daily_bars")
    op.drop_table("instruments")
    op.drop_index(op.f("ix_holdings_security_id"), table_name="holdings")
    op.drop_column("holdings", "isin")
    op.drop_column("holdings", "security_id")
