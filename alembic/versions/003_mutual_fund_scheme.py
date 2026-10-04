"""Mutual fund scheme master table (Workstream B, B1)

Revision ID: 003_mutual_fund_scheme
Revises: 002_market_data
Create Date: 2026-10-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_mutual_fund_scheme"
down_revision: str | None = "002_market_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mutual_fund_schemes",
        sa.Column("scheme_code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("isin", sa.String(length=20), nullable=True),
        sa.Column("fund_house", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("sebi_group", sa.String(length=32), nullable=True),
        sa.Column("plan", sa.String(length=16), nullable=True),
        sa.Column("option", sa.String(length=16), nullable=True),
        sa.Column("latest_nav", sa.Float(), nullable=True),
        sa.Column("nav_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scheme_code"),
    )
    op.create_index(op.f("ix_mutual_fund_schemes_fund_house"), "mutual_fund_schemes", ["fund_house"], unique=False)
    op.create_index(op.f("ix_mutual_fund_schemes_sebi_group"), "mutual_fund_schemes", ["sebi_group"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mutual_fund_schemes_sebi_group"), table_name="mutual_fund_schemes")
    op.drop_index(op.f("ix_mutual_fund_schemes_fund_house"), table_name="mutual_fund_schemes")
    op.drop_table("mutual_fund_schemes")
