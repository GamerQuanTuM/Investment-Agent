from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from investment_agent.config.settings import get_settings
from investment_agent.db.models.base import Base, TimestampMixin


class ChatMemory(Base, TimestampMixin):
    """One chat message plus its embedding, for semantic recall across a session."""

    __tablename__ = "chat_memory"

    session_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(get_settings().EMBEDDING_DIMENSIONS), nullable=False)

    __table_args__ = (
        Index(
            "ix_chat_memory_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
