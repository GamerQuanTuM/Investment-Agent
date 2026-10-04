# Indian Market Data Sources & Evidence Provenance

## 1. Hierarchy of Information Sources

To eliminate financial hallucination, the agent enforces a strict hierarchy of data sources:

1. **Exchange Regulatory Data**: National Stock Exchange of India (NSE) & Bombay Stock Exchange (BSE) official feeds.
2. **Statutory Regulators**: Securities and Exchange Board of India (SEBI) and Association of Mutual Funds in India (AMFI).
3. **Official Company Filings**: Audited annual reports, financial results under SEBI (LODR), DRHP/RHP draft prospectuses, investor presentations.
4. **Reliable Financial Databases**: Structured company financials (Screener.in, Trendlyne, Yahoo Finance / yfinance).
5. **Reputable Financial Journalism**: The Economic Times, Mint, Business Standard (used strictly for contextual news, not audited financials).
6. **Disallowed**: Unverified blogs, social media tips, anonymous forums.

## 2. Evidence Object Structure

Every numerical and factual statement is bound to an `Evidence` object:

```python
class Evidence(BaseModel):
    claim: str
    source_url: str
    source_name: str
    source_type: SourceType  # NSE, BSE, SEBI, AMFI, COMPANY_FILING, etc.
    published_at: datetime | None
    retrieved_at: datetime
    data_date: datetime | None
    confidence: float
```

## 3. Strict Missing-Data Handling

When data cannot be verified with primary sources:
* The system emits: `DATA_UNAVAILABLE` or `INSUFFICIENT_EVIDENCE`.
* It never guesses, extrapolates, or estimates numbers without explicit labels.
