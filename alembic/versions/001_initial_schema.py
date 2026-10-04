"""Initial schema with users, investment_profiles, portfolios, holdings, prediction_logs, and strategy_versions

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-09-30 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # Investment profiles table
    op.create_table(
        "investment_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("monthly_budget", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("investment_horizon_years", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("risk_tolerance", sa.String(length=50), nullable=False, server_default="moderate"),
        sa.Column("financial_goal", sa.String(length=255), nullable=False),
        sa.Column("max_single_stock_allocation_pct", sa.Float(), nullable=False, server_default="15.0"),
        sa.Column("max_sector_allocation_pct", sa.Float(), nullable=False, server_default="25.0"),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # Portfolios table
    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, server_default="Main Portfolio"),
        sa.Column("cash_available", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolios_user_id"), "portfolios", ["user_id"], unique=False)

    # Holdings table
    op.create_table(
        "holdings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("portfolio_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=False, server_default="General"),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("average_buy_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("metadata_info", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_holdings_asset_id"), "holdings", ["asset_id"], unique=False)
    op.create_index(op.f("ix_holdings_portfolio_id"), "holdings", ["portfolio_id"], unique=False)

    # Prediction Logs table (immutable logging)
    op.create_table(
        "prediction_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prediction_id", sa.String(length=50), nullable=False),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False, server_default="stock"),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("thesis", sa.String(length=2000), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("expected_conditions", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RESEARCH"),
        sa.Column("model_provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("strategy_version", sa.String(length=50), nullable=False),
        sa.Column("evaluation_due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_status", sa.String(length=50), nullable=True),
        sa.Column("evaluation_notes", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prediction_logs_asset_id"), "prediction_logs", ["asset_id"], unique=False)
    op.create_index(op.f("ix_prediction_logs_prediction_id"), "prediction_logs", ["prediction_id"], unique=True)
    op.create_index(op.f("ix_prediction_logs_user_id"), "prediction_logs", ["user_id"], unique=False)

    # Strategy Versions table
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("evaluation_results", sa.JSON(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategy_versions_version"), "strategy_versions", ["version"], unique=True)


def downgrade() -> None:
    op.drop_table("strategy_versions")
    op.drop_table("prediction_logs")
    op.drop_table("holdings")
    op.drop_table("portfolios")
    op.drop_table("investment_profiles")
    op.drop_table("users")
