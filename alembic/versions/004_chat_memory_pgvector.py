"""Chat memory with pgvector: enable the extension, store embedded chat messages

Revision ID: 004_chat_memory_pgvector
Revises: 003_mutual_fund_scheme
Create Date: 2026-10-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "004_chat_memory_pgvector"
down_revision: str | None = "003_mutual_fund_scheme"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 768  # keep in step with EMBEDDING_DIMENSIONS in settings


def upgrade() -> None:
    # Needs the pgvector build of Postgres (docker image pgvector/pgvector:pg16) and a role
    # allowed to create extensions.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "chat_memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_memory_session_id"), "chat_memory", ["session_id"], unique=False)
    op.execute(
        "CREATE INDEX ix_chat_memory_embedding ON chat_memory "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_index("ix_chat_memory_embedding", table_name="chat_memory")
    op.drop_index(op.f("ix_chat_memory_session_id"), table_name="chat_memory")
    op.drop_table("chat_memory")
    # The extension is left installed: other tables may use it.
