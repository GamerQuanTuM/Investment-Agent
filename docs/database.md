# Database Schema & Storage Separation

## 1. Storage Strategy: Structured vs Unstructured

The architecture strictly segregates relational structured data from semantic vector representations:

* **PostgreSQL**:
  * Users & Investment Profiles (`users`, `investment_profiles`)
  * Portfolios, Holdings, and Transactions (`portfolios`, `holdings`)
  * Financial metrics, ratios, historical prices
  * Immutable prediction tracking & reality monitoring (`prediction_logs`)
  * Strategy versions and rules (`strategy_versions`)
* **Qdrant Vector Database**:
  * Regulatory filings, DRHP/RHP draft prospectuses
  * Earnings call transcripts, Annual reports (MD&A)
  * Investor presentations, Brokerage research notes
* **Redis**:
  * Low-latency price caches, rate limit tracking, intermediate session states

## 2. PostgreSQL Relational Schema

```text
users
├── id (UUID)
├── email (VARCHAR, unique)
├── name (VARCHAR)
└── is_active (BOOLEAN)

investment_profiles
├── id (UUID)
├── user_id (UUID, FK -> users.id)
├── monthly_budget (FLOAT)
├── investment_horizon_years (INT)
├── risk_tolerance (VARCHAR)
├── max_single_stock_allocation_pct (FLOAT)
└── max_sector_allocation_pct (FLOAT)

portfolios
├── id (UUID)
├── user_id (UUID, FK -> users.id)
├── name (VARCHAR)
├── cash_available (FLOAT)
└── currency (VARCHAR)

holdings
├── id (UUID)
├── portfolio_id (UUID, FK -> portfolios.id)
├── asset_id (VARCHAR)
├── symbol (VARCHAR)
├── quantity (FLOAT)
├── average_buy_price (FLOAT)
└── current_price (FLOAT)

prediction_logs
├── id (UUID)
├── prediction_id (VARCHAR, unique)
├── asset_id (VARCHAR)
├── thesis (TEXT)
├── assumptions (JSON)
├── model_provider (VARCHAR)
├── model_name (VARCHAR)
├── prompt_version (VARCHAR)
└── strategy_version (VARCHAR)
```

## 3. Database Migrations (Alembic)

All schema changes are versioned using Alembic.
* Configuration: `alembic.ini` and `alembic/env.py`
* Migration scripts: `alembic/versions/`
* Execute migrations:
  ```bash
  uv run alembic upgrade head
  ```
