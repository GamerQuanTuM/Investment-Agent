# AI Investment Research & Portfolio Guidance Agent (Indian Market)

Production-oriented, evidence-based AI Investment Research and Portfolio Guidance Agent tailored specifically for the Indian equity and mutual fund universe (NSE, BSE, SEBI, AMFI).

Built with **Python 3.12+**, `uv`, **FastAPI**, **LangChain**, **LangGraph**, **PostgreSQL**, and **Redis**.

---

## 1. Core Architecture & Philosophy

The system strictly divides duties into two independent layers to protect user privacy and enforce analytical discipline:

* **Layer A — Research Engine**: Researches the Indian investment universe (stocks, ETFs, mutual funds, IPOs, corporate announcements) completely independently of any user. Never holds personal data.
* **Layer B — Personal Investment Agent**: Consumes research outputs from Layer A and evaluates them against the user's risk profile, monthly budget, existing portfolio concentration, and investment horizon (3–5 years).

### Strict Safety & Anti-Hallucination Behavior
* **No Day-Trading**: Designed for disciplined 3–5 year investment horizons.
* **Zero Fabrication**: Never invents financial data, prices, P/E ratios, or predictions.
* **Truth in Evidence**: When data is missing, the system outputs `DATA_UNAVAILABLE` or `INSUFFICIENT_EVIDENCE`.
* **Explicit Fact vs. Analysis**: Every brief strictly partitions `FACT`, `INTERPRETATION`, `ASSUMPTION`, `UNCERTAINTY`, and `RISK`.
* **Deterministic Calculations**: Ratios, CAGR, allocations, and drawdowns are computed in Python—never by an LLM.

---

## 2. Multi-Model LLM Routing Architecture

The system never hardcodes a single LLM provider. It dynamically routes tasks to specialized tiers through environment variables:

| Tier | Default Provider | Default Model | Responsibility |
| :--- | :--- | :--- | :--- |
| **Primary** | OpenAI | `gpt-4o` | Structured thesis synthesis & final report generation |
| **Cheap** | Groq | `llama-3.3-70b-versatile` | High-throughput data extraction, filtering, and initial parsing |
| **Reasoning** | Anthropic | `claude-3-7-sonnet-20250219` | Deep bull/bear dialectic tension and risk interrogation |
| **Local** | Ollama | `llama3.2` | Offline processing, privacy-sensitive tasks, and cost reduction |
| **Fallback** | Gemini | `gemini-2.0-flash` | Automated fallback on rate limits or API outages |

---

## 3. Prerequisites

* **Python 3.12+**
* **`uv` package manager** (installed via `curl -LsSf https://astral.sh/uv/install.sh` or `winget install --id=astral-sh.uv`)
* **Docker & Docker Compose** (for PostgreSQL and Redis)

---

## 4. Installation & Setup

1. **Clone & Enter Workspace**:
   ```bash
   cd AI-Investment-Research-And-Portfolio-Guidance-Agent
   ```

2. **Install Dependencies using `uv`**:
   ```bash
   uv sync
   ```

3. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your LLM API keys (OpenAI, Gemini, Anthropic, Groq, Ollama)
   ```

4. **Start Infrastructure Services**:
   ```bash
   docker compose up -d postgres redis
   ```

5. **Apply Database Migrations (Alembic)**:
   ```bash
   uv run alembic upgrade head
   ```

---

## 5. Running the Application

### Start Development Server
```bash
uv run uvicorn investment_agent.main:app --reload --host 0.0.0.0 --port 8000
```
* **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

### Trigger Research Graph Run
```bash
curl -X POST "http://localhost:8000/research/run" \
     -H "Content-Type: application/json" \
     -d '{"user_id": "usr_001", "monthly_budget": 25000.0}'
```

### SIP Calculator: Real Mutual Funds and ETF Mixes

The full, current route list is always in Swagger at `/docs`; the mutual-fund-backed SIP
tools live under `/funds/*` (`src/investment_agent/api/routes/funds.py`), separate from
the listed-ETF-mix calculator at `POST /research/sip` (`src/investment_agent/research/sip.py`).

```bash
# Search the AMFI scheme master (falls back to mfapi.in if it hasn't been synced yet)
curl "http://localhost:8000/funds/search?q=sbi+bluechip"

# One scheme's facts, trailing returns, and risk metrics
curl "http://localhost:8000/funds/119598"

# Backtest a real historical SIP against that scheme's actual NAV history
curl -X POST "http://localhost:8000/funds/sip/backtest" \
     -H "Content-Type: application/json" \
     -d '{"scheme_code": "119598", "monthly": 5000}'

# Forward projection (an assumption, not a forecast — always labelled as such)
curl -X POST "http://localhost:8000/funds/sip/project" \
     -H "Content-Type: application/json" \
     -d '{"monthly": 5000, "years": 10, "annual_return_pct": 12}'

# Deterministic, risk-profile-weighted mix across multiple funds
curl -X POST "http://localhost:8000/funds/sip/suggest" \
     -H "Content-Type: application/json" \
     -d '{"monthly": 10000, "horizon_years": 10, "risk_profile": "moderate"}'
```

The AMFI-backed `mutual_fund_schemes` table (used by `GET /funds/search` and
`POST /funds/sip/suggest`'s fund-picking step) is populated by `POST /market/refresh`;
until that's run at least once, both routes degrade gracefully (search falls back to
mfapi.in's own unclassified search; suggest returns a `DATA_UNAVAILABLE` sleeve per
category) rather than erroring. See `docs/data-sources.md` §4 for the data-source detail.

### Chat Assistant

`POST /research/chat` understands a beginner's own words. A structured intent step (cheap
model → validated JSON, deterministic rules as fallback) picks one of `education`,
`stock_list`, `stock_single`, `plan_sip_fund`, `plan_sip_etf`, `fund_list`, `market_overview`,
`portfolio_help`, `off_topic` or `unclear`, and fills slots (amount, lump sum vs monthly,
horizon, risk, stock count, experience) from everything said in one message.

```bash
curl -s -X POST http://localhost:8000/research/chat -H "Content-Type: application/json"   -d '{"session_id": "demo", "message": "I am new. Suggest 10-12 stocks for 10000 rupees"}'
curl -s -X POST http://localhost:8000/research/chat -H "Content-Type: application/json"   -d '{"session_id": "demo", "message": "what is an ETF?"}'
```

Tickers only ever come from the stock master in the database, never from the model.
"N stocks for ₹X" is selected and sized entirely in Python (whole shares, sector and
market-cap caps, leftover cash reported, honest small-budget reality check); a model may only
phrase the result and its text is dropped if it contains any ticker or number not in the
result. The stock list needs `POST /market/refresh` and `POST /market/fundamentals` to have
run, otherwise the reply says market data isn't loaded. Sessions live in Redis
(`chat:{session_id}`, 24 h) with an in-memory fallback. Full details: [`docs/chat.md`](docs/chat.md).

---

## 6. Running Tests & Code Quality

```bash
# Run complete test suite (28+ tests passing)
uv run pytest -v

# Run specific test suites
uv run pytest tests/unit -v
uv run pytest tests/graph -v
uv run pytest tests/integration -v

# Code formatting & linting
uv run ruff check src tests
uv run ruff format src tests

# Static type verification
uv run mypy src
```

---

## 7. Project Documentation

Detailed architecture and design specifications are maintained in [`docs/`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs):

* [`docs/architecture.md`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs/architecture.md): Two-layer architecture and component separation.
* [`docs/llm-providers.md`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs/llm-providers.md): Dynamic multi-provider factory, routing tiers, and fallback chains.
* [`docs/data-sources.md`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs/data-sources.md): Indian market primary sources (NSE, BSE, SEBI, AMFI) and evidence schemas.
* [`docs/self-correction.md`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs/self-correction.md): Immutable prediction logs, reality monitoring, and strategy versioning.
* [`docs/graph-workflow.md`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs/graph-workflow.md): LangGraph state graph specification and short-circuit gating.
* [`docs/chat.md`](docs/chat.md): Chat intents, slot filling, sessions, stock-list planner and response contract.
* [`docs/database.md`](file:///d:/Technical/Python/Agents/AI-Investment-Research-And-Portfolio-Guidance-Agent/docs/database.md): PostgreSQL schema, Alembic migrations, and Redis usage.

---

## 8. Adding a New LLM Provider

1. Open `src/investment_agent/llm/providers.py` and append provider enum (e.g. `MISTRAL = "mistral"`).
2. In `src/investment_agent/llm/factory.py`, add the provider branch inside `create_chat_model` returning the appropriate LangChain model.
3. Add configuration keys in `src/investment_agent/config/settings.py` and `.env.example`.
4. Add unit test in `tests/unit/test_llm_factory.py`.
