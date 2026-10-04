# Self-Correction & Reality Monitoring

## 1. Immutability Principle: Never Rewrite History

The agent must never edit or overwrite past investment predictions, theses, or recommendations.
Every prediction is logged into `prediction_logs` with:
* `prediction_id`: Unique identifier
* `asset_id`: Target stock / ETF / mutual fund
* `thesis`: Core thesis statement
* `assumptions`: Explicit testable conditions (e.g. `Revenue growth >= 12%`)
* `model_provider`, `model_name`: Exact LLM used
* `prompt_version`: Version of the prompt used (e.g. `v1.0.0`)
* `strategy_version`: Active investment rule version (e.g. `1.0.0`)

## 2. Reality Monitoring Lifecycle

After predefined horizons (1 month, 3 months, 6 months, 12 months), reality checks run against actual audited outcomes:

```text
Original assumption:
  Operating margin >= 24%

Actual quarterly outcome:
  Operating margin = 20.5%

Outcome Status:
  ASSUMPTION_FAILED
```

## 3. Standardized Error Taxonomy

When an assumption or prediction fails, it is classified under `ErrorTaxonomy`:
* `DATA_ERROR`: Feed had stale or corrupted numbers.
* `SOURCE_ERROR`: Source misrepresented corporate action.
* `CALCULATION_ERROR`: Mathematical discrepancy.
* `REASONING_ERROR`: Faulty logic connecting evidence to conclusion.
* `ASSUMPTION_ERROR`: Macro or industry dynamics changed unexpectedly.
* `TIMING_ERROR`: Horizon was insufficient for thesis realization.
* `THESIS_ERROR`: Core investment premise was fundamentally flawed.
* `MODEL_ERROR`: LLM misread structured data or ignored instructions.
* `INSUFFICIENT_DATA`: Critical data was omitted.
* `EXTERNAL_EVENT`: Force majeure, unexpected geopolitical or regulatory shock.

## 4. Controlled Strategy Versioning

The agent never updates strategy rules autonomously based on a single negative outcome.
Instead, proposed rule modifications are logged to `strategy_versions` and require human approval before activation.
