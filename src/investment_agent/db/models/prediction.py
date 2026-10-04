from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from investment_agent.db.models.base import Base, TimestampMixin


class PredictionLog(Base, TimestampMixin):
    __tablename__ = "prediction_logs"

    prediction_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock", nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    thesis: Mapped[str] = mapped_column(String(2000), nullable=False)
    assumptions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expected_conditions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RESEARCH", nullable=False)

    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(50), nullable=False)

    evaluation_due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    outcome_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evaluation_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class StrategyVersion(Base, TimestampMixin):
    __tablename__ = "strategy_versions"

    version: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    changes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    evaluation_results: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approved: Mapped[bool] = mapped_column(default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
