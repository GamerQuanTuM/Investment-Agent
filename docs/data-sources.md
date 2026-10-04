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

## 4. Mutual Fund Data Sources (Workstream B)

Two free, keyless sources back the real-mutual-fund SIP tools under `/funds/*`
(`api/routes/funds.py` — see the FastAPI Swagger docs at `/docs` for the full route list):

* **AMFI (`AMFI_NAV_URL`, `market/amfi.py`)** — the full `NAVAll.txt` scheme master,
  synced into the `mutual_fund_schemes` table (`sync_mutual_fund_schemes`, triggered by
  `POST /market/refresh`). Gives every scheme's fund house, category, and three
  **deterministic** (no LLM) classifications computed from that text: `plan`
  (direct/regular), `option` (growth/IDCW), and `sebi_group` (large/mid/small/flexi/elss/
  index/debt/hybrid/gold/other).
* **mfapi.in (`market/mfapi.py`)** — free, keyless full NAV history and scheme search.
  Verified reachable from this project's usual network environment, unlike
  `nseindia.com`/`api.bseindia.com` (both Akamai-blocked from this project's sandbox — see
  `market/nse.py`'s module docstring). Used for `GET /funds/search` (falls back here when
  the local scheme master has no match), `GET /funds/{scheme_code}`, and every backtest/
  projection route — real historical NAVs, not synthetic ones.

**Known, disclosed gap**: neither source carries a fund's expense ratio (TER). Every
function that would need it (`portfolio/fund_metrics.py::expense_ratio_drag`,
`suggest_mix`'s "lowest expense ratio" selection criterion from the original spec) either
isn't wired into a route yet or explicitly skips that criterion — ranking or computing on
a guessed TER would violate the no-fabricated-numbers rule. If a free TER source is added
later, wire it through `market/<name>.py` the same way as every other provider here.

**Mutual fund tax assumptions** (`portfolio/fund_metrics.py::ltcg_stcg_estimate`):
₹1.25L LTCG exemption, 12.5% LTCG / 20% STCG for **equity-oriented** funds only (these are
module-level constants, not a Settings/env-var — they're tax-law constants, not
deployment config). Debt fund gains are taxed at the investor's income slab rate, which
this project has no way to know, so the estimate deliberately returns `DATA_UNAVAILABLE`
for `is_equity=False` rather than guessing a rate.
