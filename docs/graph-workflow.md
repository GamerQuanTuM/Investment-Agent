# LangGraph Multi-Agent Workflow

## 1. Graph State

The pipeline passes a typed `InvestmentGraphState` containing Layer A (universe research) and Layer B (user portfolio) contexts:

```python
class InvestmentGraphState(TypedDict, total=False):
    user_id: str
    user_profile: dict[str, Any]
    portfolio: dict[str, Any]
    monthly_budget: float

    market_context: dict[str, Any]
    candidates: list[dict[str, Any]]
    research_documents: list[dict[str, Any]]

    fundamental_analysis: dict[str, Any]
    valuation_analysis: dict[str, Any]
    bull_case: dict[str, Any]
    bear_case: dict[str, Any]
    risk_analysis: dict[str, Any]
    portfolio_impact: dict[str, Any]

    evidence: list[dict[str, Any]]
    contradictions: list[str]

    recommendation: dict[str, Any]
    confidence: float
    evidence_quality: str

    errors: list[str]
    warnings: list[str]
    execution_status: str
```

## 2. Graph Topology & Token-Saving Short-Circuits

```text
START
  │
  ▼
Load User Profile
  │
  ▼
Load Portfolio
  │
  ▼
Load Research Universe
  │
  ▼
Market Data Validation
  │
  ▼
Candidate Screening (Deterministic Filters)
  │
  ├─────────────────────────────────────────────────┐
  │ [Candidates Pass]                               │ [0 Candidates Pass]
  ▼                                                 ▼
Fundamental Analysis ──► News Analysis         Recommendation Gate (NO ACTION)
  │                                                 │
  ▼                                                 ▼
Valuation Analysis                             Recommendation Logger
  │                                                 │
  ▼                                                 ▼
Risk Agent (Reasoning LLM)                         END
  │
  ▼
Bull Case Agent
  │
  ▼
Bear Case Agent (Falsification check)
  │
  ▼
Portfolio Impact Agent (Concentration checks)
  │
  ▼
Evidence Verifier (Anti-Hallucination check)
  │
  ▼
Recommendation Gate ──────────┐
  │ [Opportunity]             │ [Rejected / Insufficient Evidence]
  ▼                           ▼
Investment Report        Recommendation Logger
  │                           │
  ▼                           ▼
Recommendation Logger        END
  │
  ▼
 END
```

## 3. Mandatory Output Fact-Separation

The final report strictly categorizes insights:
* **FACT**: Verifiable historical and financial data backed by source metadata.
* **INTERPRETATION**: Analytical deduction derived strictly from stated facts.
* **ASSUMPTION**: Required operational condition for the thesis to hold.
* **UNCERTAINTY**: Information gaps that the system cannot confidently resolve.
* **RISK**: Asymmetric downside catalysts and regulatory/macro sensitivities.
