from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    SEBI = "SEBI"
    AMFI = "AMFI"
    COMPANY_FILING = "Company Filing"
    ANNUAL_REPORT = "Annual Report"
    INVESTOR_PRESENTATION = "Investor Presentation"
    EXCHANGE_ANNOUNCEMENT = "Exchange Announcement"
    REPUTABLE_NEWS = "Reputable News"
    FINANCIAL_DATA_PROVIDER = "Financial Data Provider"
    INDSTOCKS = "INDstocks"
    OTHER = "Other"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Evidence(BaseModel):
    claim: str
    source_url: str = ""
    source_name: str
    source_type: SourceType = SourceType.OTHER
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    data_date: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceVerificationResult(BaseModel):
    is_valid: bool
    verified_claims_count: int
    unsupported_claims_count: int
    unsupported_claims: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    quality_score: float = 1.0  # 0.0 to 1.0
    status: str = "VERIFIED"  # "VERIFIED", "INSUFFICIENT_EVIDENCE", "DATA_UNAVAILABLE"
