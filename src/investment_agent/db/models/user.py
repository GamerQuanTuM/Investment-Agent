from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from investment_agent.db.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    profile: Mapped["InvestmentProfile"] = relationship(
        "InvestmentProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    portfolios: Mapped[list["Portfolio"]] = relationship(  # type: ignore # noqa: F821
        "Portfolio",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class InvestmentProfile(Base, TimestampMixin):
    __tablename__ = "investment_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    monthly_budget: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    investment_horizon_years: Mapped[int] = mapped_column(default=5, nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(String(50), default="moderate", nullable=False)
    financial_goal: Mapped[str] = mapped_column(
        String(255),
        default="Long-term wealth accumulation",
        nullable=False,
    )
    max_single_stock_allocation_pct: Mapped[float] = mapped_column(
        Float, default=15.0, nullable=False
    )
    max_sector_allocation_pct: Mapped[float] = mapped_column(Float, default=25.0, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="profile")
