# Implementation Progress — Investment Agent expansion

This file tracks progress against two specs the user has handed me, tracked as separate
workstreams below. **Rule for future sessions:** read this file top to bottom before
starting new work. Update the relevant checkboxes and the "Currently in progress" section
as you go — not just at the end. Run `ruff check`, `mypy`, `pytest` (backend) and
`pnpm lint && pnpm build` (frontend) before marking any step done.

**Known environment issue:** the backend's `uvicorn --reload` process in the user's terminal
does not reliably hot-reload on file save — changes have taken anywhere from 5 to 30+
seconds, or required a manual restart. Verify backend changes with a direct `curl` test
after editing; if a stale response persists after ~20s, tell the user to restart the
backend terminal rather than assuming the edit is broken.

**Known pre-existing issues (not caused by this work, do not "fix" as a side effect unless
asked — just don't let them block an unrelated step):**
- `mypy src` fails on 10 pre-existing errors in `market/universe.py`, `market/sync.py`,
  `research/guidance.py` (Optional-handling issues, unrelated to any work done so far).
- `pytest tests/unit/test_settings.py::test_settings_defaults` fails in this environment
  because the real `REDIS_HOST`/`REDIS_URL` env resolves to an `rediss://` (TLS) Upstash
  URL, but the test hard-asserts `"redis://" in resolved_redis_url`. Pre-existing, unrelated
  to Redis-cache work below.

---

## Workstream A — Gaps/Features/UI spec (Part 1/2/3, 8 delivery steps)

Source: the big pasted spec covering cache/evidence/scoring/filings/news/macro/funds/
portfolio/alerts/compare, Part 3 UI pages. Delivered in 8 PR-sized steps, in order.

- [x] **Step 1** — Gaps 6, 3, 10 (cache, SourceType, test scaffolding) — **DONE, see below**
- [x] **Step 2** — F1 filings/shareholding + gaps 1, 2 + Stock detail Filings/Shareholding tabs — **DONE, see below**
- [x] **Step 3** — F2 scoring + gaps 4, 5 + ScoreRing UI — **DONE, see below**
- [x] **Step 4** — F4 news + news_risk + News tab — **DONE, see below**
- [x] **Step 5** — F3 macro + Market Mood strip — **DONE, see below**
- [x] **Step 6** — superseded by Workstream B, no separate action needed — **see note below**
- [x] **Step 7** — F7 portfolio + gap 8 + /portfolio page — **DONE, see below**
- [x] **Step 8** — F8 alerts, F9 compare, gap 7 outcome scoring — **DONE, see below**

### Step 1 — DONE

- [x] Gap 6 — `market/cache.py` rewritten: one shared module-level `Redis` client (lazy
      singleton via `_get_client()`) instead of opening/closing a connection per call.
      `init_cache()` / `close_cache()` wired into `main.py`'s lifespan. Added `CacheTTL` enum
      (`PRICE=60s`, `FILINGS=1h`, `FUNDAMENTALS=24h`). Wired into
      `market/yahoo_market.py`: `quote_symbol` (PRICE) and `company_fundamentals`
      (FUNDAMENTALS) are now cache-first. `chart_symbol`, `screen_movers`, `index_quotes`
      still uncached — intentionally left for a later step that touches those paths.
- [x] Gap 3 (SourceType part only — BSE/NSE providers themselves are Step 2/F1) — added
      `MFAPI`, `RBI`, `NEWS_RSS`, `FRED` to `research/evidence.py` `SourceType` enum.
- [x] Gap 10 — test scaffolding under `tests/unit/market/`:
      - `tests/unit/market/conftest.py` — `load_fixture` fixture (factory pattern, reads
        JSON from `tests/unit/market/fixtures/`) and `no_redis` fixture (monkeypatches a
        provider module's `cache_get`/`cache_set` to no-ops so tests never touch real Redis).
      - `tests/unit/market/fixtures/yahoo_quote_tcs.json` — recorded/representative Yahoo
        `v7/finance/quote` response shape.
      - `tests/unit/market/test_yahoo_market.py` — 3 tests using `respx` to mock the
        crumb/cookie handshake + quote endpoint: happy path, empty-result path, and the
        401-retry path (regression test for the earlier crumb-revocation fix).
      - Added `respx>=0.22.0` to `[dependency-groups] dev` in `pyproject.toml` (new dep,
        `uv sync` already run).
      - **Pattern for future provider tests** (BSE/NSE/RBI/FRED/MFAPI/news RSS in later
        steps): record a trimmed real response → `tests/unit/market/fixtures/<name>.json` →
        mock with `respx` → assert on parsed/normalized output, not the raw fixture. If the
        new provider's module imports `cache_get`/`cache_set` from `market/cache.py`, add it
        to the `for module in (...)` tuple in `conftest.py`'s `no_redis` fixture.
      - All green: `ruff check src tests` clean, `mypy` on the 3 changed files clean,
        `pytest tests/unit/market -v` 3/3 pass, full `pytest` suite passes except the two
        pre-existing failures noted above (unaffected by this step).

Files touched this step:
- `src/investment_agent/market/cache.py` (rewritten)
- `src/investment_agent/main.py` (lifespan hooks)
- `src/investment_agent/market/yahoo_market.py` (cache wiring + import)
- `src/investment_agent/research/evidence.py` (SourceType additions)
- `pyproject.toml` (added respx dev dep)
- `tests/unit/market/conftest.py`, `tests/unit/market/fixtures/yahoo_quote_tcs.json`,
  `tests/unit/market/test_yahoo_market.py` (new)

### Step 2 — DONE

**Verified network finding (read this before trusting any "live" NSE/BSE test from this
sandbox):** both `api.bseindia.com` and `www.nseindia.com` returned a hard `403` from
Akamai on a plain homepage GET, tried with several realistic browser header sets — this
looks like an IP/network-level block on this sandbox's egress, not a header problem (Yahoo
also 429'd shortly after, from unrelated rate limiting earlier in the same session). **None
of the NSE code below has been exercised against the live API.** Correctness rests on
matching NSE's documented/widely-used public endpoint shapes and on the respx-mocked tests.
Verify live once this runs on the user's actual deployment network, and adjust field names
in `market/nse.py`'s `_normalize_announcement`/`_normalize_shareholding_quarter` if NSE's
response shape has drifted from what's assumed there.

**Chose NSE over BSE for F1** (spec listed BSE first): BSE's announcement/shareholding
endpoints are keyed by a numeric scrip code (e.g. TCS = 532540) and there's no existing
symbol→BSE-scrip-code mapping anywhere in this codebase (INDstocks instruments are NSE
symbol-keyed only) — building that mapping is a non-trivial separate task. NSE's endpoints
take the plain NSE trading symbol directly, which the rest of the app already keys
everything by, so it composes with zero extra plumbing. Revisit BSE as a second source
later if NSE coverage proves unreliable in practice.

- [x] **F1 filings/shareholding** — `src/investment_agent/market/nse.py` (new): Akamai
      cookie warm-up (mirrors Yahoo's crumb pattern in `yahoo_market.py`), `get_filings(symbol)`
      (NSE corporate-announcements), `get_shareholding(symbol)` (NSE
      corporate-shareholding-pattern, quarter-wise promoter/FII/DII/public % + promoter
      pledge), `latest_promoter_pledge_pct(quarters)` helper. Every function degrades to
      `[]` on any failure — never raises. Cached via Gap-6's `CacheTTL.FILINGS` (1h).
      **Latency fix found while wiring this in** (see Gap 1 below): a bare per-candidate
      retry with the original 20s httpx timeout, serialized through one module-level
      session lock, turned a single `/research/run` call into an **11-minute** test run
      once candidates existed in the DB (N candidates × ~slow-timeout, serialized). Fixed
      with (a) a tight `httpx.Timeout(connect=3, read=5, write=5, pool=3)`, (b) a
      `_blocked_until` cooldown (90s) so a failed warm-up short-circuits instantly for every
      other candidate in the same run instead of re-attempting per symbol, and (c) an
      `asyncio.wait_for(..., timeout=10)` wrapper in `news_analysis_node` as defense in
      depth. Confirmed fix: the same integration test that took 672s now takes 3.4s. **If
      adding more NSE-calling code later, reuse `_blocked_until`/`_TIMEOUT` rather than
      re-introducing an unbounded per-candidate retry.**
      New routes: `GET /market/stocks/{symbol}/filings`, `GET /market/stocks/{symbol}/shareholding`
      (`api/routes/market.py`), both returning `{symbol, status: OK|DATA_UNAVAILABLE, ...}`.
- [x] **Gap 1** — `news_analysis_node` (`graph/nodes.py`) now fetches live NSE filings per
      candidate (concurrently, with the timeout guard above) instead of reading a
      `candidate.get("recent_announcements")` field nothing ever populated. Computes
      `filings_risk` (NORMAL/ELEVATED/DATA_UNAVAILABLE) via a keyword screen over filing
      subjects (resignation/default/insolvency/fraud/etc.) — **this is a keyword heuristic
      over real filings, not sentiment analysis**; full NLP/LLM sentiment classification is
      still F4 (Step 4) and should replace `filings_risk` with a model-scored signal then.
      `risk_agent_node`'s `news_risk` now reads this instead of a hardcoded
      `"DATA_UNAVAILABLE"`. `investment_report_node`'s `UNCERTAINTY` line now reflects the
      real filings status instead of a hardcoded "until an exchange filing is ingested"
      string that could never become true.
- [x] **Gap 2** — automatic fundamentals ingest, independent of INDstocks (free/keyless data
      shouldn't require a broker to sync):
      - `portfolio/calculations.py`: added `calculate_fcf(ocf, capex)` and
        `derive_ratios_from_statements(statements)` (pure, unit-tested) — computes
        `roce_pct`, `fcf`, `revenue_growth_3y_cagr_pct`, `profit_growth_3y_cagr_pct` from
        annual statement history, returning `None` (not 0 or a guess) for anything the
        source doesn't have enough data points for.
      - `market/yahoo_market.py`: added `financial_statement_history(symbol, exchange)` —
        fetches `incomeStatementHistory`/`balanceSheetHistory`/`cashflowStatementHistory`
        via the same quoteSummary endpoint `company_fundamentals` already uses, cached under
        `CacheTTL.FUNDAMENTALS` (24h).
      - `market/sync.py`: new `sync_fundamentals(settings, symbols=None)` — for each
        watchlist symbol (`settings.indstocks_watchlist`), pulls Yahoo fundamentals +
        statements + NSE shareholding (for promoter pledge), computes ratios, and writes via
        the existing `store_fundamental_snapshots`. `refresh_market_data()` now calls this
        *before* its `indstocks_configured` gate (wrapped in try/except, appended to
        `summary["warnings"]`), so `POST /market/refresh` syncs fundamentals even for users
        without a broker connected — previously the whole function raised immediately if
        INDstocks wasn't configured, running nothing. No new DB column for FCF — it rides in
        the existing `raw_payload` JSON field on `FundamentalSnapshot` rather than forcing a
        migration mid-step; revisit if FCF needs to be a queryable column later.
- [x] **Frontend** — Stock detail page (`app/stocks/[symbol]/page.tsx`) gained two tabs:
      - **Filings**: timeline list (category badge, date, subject, "View filing" link to the
        PDF attachment when present), with the standard loading-skeleton /
        `DATA_UNAVAILABLE`-tile / error states.
      - **Shareholding**: per-quarter stacked bar (Promoter/FII/DII/Public, color-coded) with
        the promoter pledge % called out per quarter (red if >0%, green if 0%).
      New types (`Filing`, `StockFilings`, `ShareholdingQuarter`, `StockShareholding`) in
      `lib/types.ts`, new `fetchFilings`/`fetchShareholding` in `lib/api.ts`.
- [x] **Tests** (`tests/unit/market/`): `test_nse.py` — 4 tests (filings parse + risk-keyword
      shape, 403-degrades-to-empty, shareholding parse + pledge helper, pledge-helper
      edge cases), plus 2 new fixtures (`nse_announcements_tcs.json`,
      `nse_shareholding_tcs.json`). `test_calculations.py` — 4 new tests for `calculate_fcf`
      and `derive_ratios_from_statements` (happy path with hand-computed CAGR/ROCE/FCF, and
      the all-`None`-on-missing-data path). **Bug the tests caught and the fix applied:**
      `_normalize_shareholding_quarter` used `row.get("pledge") or row.get(...)`, which
      silently turned a legitimate `0.0` pledge into `None` because `0.0` is falsy in Python
      — replaced with a `_first_present()` helper that checks `is not None` instead of
      truthiness. Same bug pattern doesn't exist elsewhere in `nse.py`, but worth checking
      for in any future provider that merges multiple possible source-field names.
      All green: `ruff check src tests`, `mypy` on every touched file, full `pytest` suite
      (50 passed, same 1 pre-existing failure as before this step) in ~20s,
      `pnpm lint && pnpm build` clean.

Files touched this step:
- `src/investment_agent/market/nse.py` (new)
- `src/investment_agent/api/routes/market.py` (2 new routes)
- `src/investment_agent/graph/nodes.py` (news_analysis_node rewrite, risk_agent_node fix,
  investment_report_node UNCERTAINTY fix, asyncio/get_filings imports)
- `src/investment_agent/portfolio/calculations.py` (calculate_fcf, derive_ratios_from_statements,
  _cagr_from_series)
- `src/investment_agent/market/yahoo_market.py` (financial_statement_history, _statement_rows)
- `src/investment_agent/market/sync.py` (sync_fundamentals, refresh_market_data restructure)
- `tests/unit/market/test_nse.py`, `tests/unit/market/fixtures/nse_announcements_tcs.json`,
  `tests/unit/market/fixtures/nse_shareholding_tcs.json` (new)
- `tests/unit/test_calculations.py` (4 new tests)
- `frontend/src/lib/types.ts` (Filing, StockFilings, ShareholdingQuarter, StockShareholding)
- `frontend/src/lib/api.ts` (fetchFilings, fetchShareholding)
- `frontend/src/app/stocks/[symbol]/page.tsx` (Filings tab, Shareholding tab)

### Step 3 — DONE

- [x] **F2 deterministic scoring** — `portfolio/scoring.py` (new, pure, no I/O): four
      sub-scores (`score_quality`, `score_valuation`, `score_momentum`, `score_risk`), each
      0-100 with every input it used listed (`ScoreInput`: label/value/unit/benchmark), plus
      `compute_overall_score` (weighted: quality 35%, valuation 30%, momentum 15%, risk
      20% — documented in-module) which **renormalizes weights** when a block is
      DATA_UNAVAILABLE rather than treating a missing block as 0. Each block returns `None`
      (not a thin/overconfident number) when fewer than half its inputs are available.
      `portfolio/calculations.py` gained the supporting pure functions:
      `calculate_interest_coverage`, `calculate_return_pct`, `calculate_distance_from_high_pct`,
      `calculate_annualized_volatility_pct`, `calculate_percentile_rank`. `derive_ratios_from_statements`
      (from Step 2) now also returns `interest_coverage`, fed by a new `interest_expense`
      field added to `yahoo_market.financial_statement_history`'s income-statement parsing.
- [x] **Gap 5 (P/E and P/B percentile)** — implemented in `research/stock_score.py` (new
      orchestration module), with an **honest approximation documented in the response
      itself** (`valuation_note`): true historical P/E needs historical EPS, which isn't
      available from a free source, so "P/E vs. own 5y history" is approximated as 5 years
      of daily closes divided by *today's* EPS — "is this price cheap relative to its own
      trading range," not a true historical P/E series. "P/E vs. sector peers" is a real,
      non-approximated percentile: current P/E of other candidates sharing this stock's
      sector, pulled from our own screened universe (`market/universe.load_candidates_from_db`,
      filtered by sector, target symbol excluded) — no external sector-P/E source needed.
- [x] **Gap 4 (replace `rule_stance`, keep it as fallback)** — integrated *lightly* into
      `research/guidance.py.guide_symbol` rather than replacing `rule_stance` outright: the
      new F2 overall score is computed best-effort (via `build_stock_score`, bounded with a
      12s `asyncio.wait_for` + broad except, so a slow/failing score can never break the
      already-shipped `/research/guidance` beginner-verdict feature) and may only **tighten**
      a `CONSIDER` down to `WAIT` when the overall score is below 50 — it can never loosen
      a `WAIT`/`AVOID` that `rule_stance`'s hard blockers produced. This mirrors the
      existing invariant `_narrate` (the LLM call) already enforces for its own opinion.
      `rule_stance` itself is untouched and remains the hard floor — "keep as fallback" is
      satisfied by construction (nothing changes when the score is unavailable). The new
      `multi_factor_score` field is additive on the response.
      **Deliberately not done:** did not make `guide_symbol` *depend on* the score (e.g. by
      fetching it instead of its own quote/chart/fundamentals) — that would have meant
      rewriting an endpoint already in active use (the beginner verdict work from an earlier
      session) for a spec item whose own wording only asks for an additive tightening.
      Revisit if the user wants deeper integration.
- [x] **Route** `GET /research/score/{symbol}?exchange=NSE` (`api/routes/research.py`) →
      `research/stock_score.py:build_stock_score` — assembles quote + 5y price history
      (Yahoo) + fundamentals/statements (Yahoo, Step 2's cache) + NSE shareholding (Step 2,
      for promoter pledge) + sector peers (DB), computes all four blocks + overall, and
      calls a CHEAP-tier LLM to narrate the finished card in plain language (2-3 sentences)
      with a deterministic fallback (`_fallback_explanation`) if that call fails — the LLM
      never sees raw statements, only the already-computed score card.
- [x] **Frontend** — new `components/ScoreRing.tsx` (circular SVG progress ring, 0-100,
      color-coded green/amber/red by threshold, renders "—" for a `None` score rather than
      a fabricated 0). New **Score** tab on the stock detail page
      (`app/stocks/[symbol]/page.tsx`): 4 `ScoreRing`s (Quality/Valuation/Momentum/Risk) +
      overall score + LLM explanation card + a "Why this {block} score" section per block
      listing every input with its value and benchmark (or a "Data unavailable" render when
      `value` is `null`) — matches the spec's "ROE 14.2% vs sector 11%" mockup row shape.
      New types (`ScoreInput`, `ScoreBlock`, `StockScore`) in `lib/types.ts`, new
      `fetchStockScore` in `lib/api.ts`.
- [x] **Tests**: `tests/unit/test_scoring.py` (14 tests covering all 4 sub-scores at their
      extremes, the "too little data → None" path, overall-score weighting, and the
      renormalize-when-a-block-is-missing path). `tests/unit/test_calculations.py` (+5 for
      the new pure functions). `tests/unit/test_stock_score.py` (2 tests, everything
      monkeypatched — this is a **wiring test**: it exists to catch a mismatched kwarg name
      or field name between `stock_score.py` and `scoring.py`, not to re-verify the scoring
      math itself). All green: `ruff check src tests`, `mypy` on every touched file (same
      one pre-existing `guidance.py` error, now at a shifted line number, nothing new),
      full `pytest` (71 passed, same 1 pre-existing failure), `pnpm lint && pnpm build` clean.
      **Caught two flawed test expectations while writing these** (not scoring bugs): two
      `test_scoring.py` cases assumed a P/E *equal to* the minimum of its comparison series
      would land at the 0th percentile — `calculate_percentile_rank` counts "at or below"
      inclusively, so equaling the minimum is a nonzero percentile. Fixed by using a P/E
      strictly below every comparison value in those two tests.

Files touched this step:
- `src/investment_agent/portfolio/scoring.py` (new)
- `src/investment_agent/portfolio/calculations.py` (5 new pure functions, `derive_ratios_from_statements`
  extended with `interest_coverage`)
- `src/investment_agent/market/yahoo_market.py` (`interest_expense` added to income statement parsing)
- `src/investment_agent/research/stock_score.py` (new)
- `src/investment_agent/research/guidance.py` (Gap 4 integration: `multi_factor_score` field,
  `_multi_factor_overall_score` helper, `asyncio` import)
- `src/investment_agent/api/routes/research.py` (`GET /score/{symbol}` route)
- `tests/unit/test_scoring.py` (new, 14 tests), `tests/unit/test_stock_score.py` (new, 2 tests),
  `tests/unit/test_calculations.py` (+5 tests, 2 existing tests updated for the new
  `interest_coverage` field)
- `frontend/src/components/ScoreRing.tsx` (new)
- `frontend/src/lib/types.ts` (`ScoreInput`, `ScoreBlock`, `StockScore`)
- `frontend/src/lib/api.ts` (`fetchStockScore`)
- `frontend/src/app/stocks/[symbol]/page.tsx` (Score tab)

### Step 4 — DONE

- [x] **`market/news.py`** (new) — Google News RSS search (`news.google.com/rss/search`),
      free and keyless. **Verified live-reachable from this environment** (confirmed via
      direct curl during development, same convention as `market/mfapi.py`). Parses
      `<item>` title/link/source/pubDate via `xml.etree.ElementTree`, normalizes `pubDate`
      (RFC 2822) to ISO-8601 UTC, degrades to `[]` (never raises) on any network/parse
      failure. Cached via a new `CacheTTL.NEWS` tier (30 min — news goes stale faster than
      filings).
- [x] **`research/sentiment.py`** (new, pure Python, no I/O) — **explicitly not an
      LLM/ML sentiment classifier**: a documented keyword lexicon (`POSITIVE_WORDS`/
      `NEGATIVE_WORDS`, ~30 terms each) scored per headline (`score_headline`) and
      aggregated across a batch of articles (`aggregate_sentiment` → label POSITIVE/
      NEUTRAL/NEGATIVE/DATA_UNAVAILABLE + counts). Same "Python computes every number"
      invariant as `portfolio/scoring.py`'s deterministic scores — this upgrades Step 2's
      narrower keyword screen (which only ever looked at exchange-filing *subjects*) to a
      broader one that runs over real news coverage, exactly as Step 2's own docstring
      said Step 4 would.
      **Real bug caught by its own test**: the first version matched words with a plain
      substring check (`word in lowered`), which matched the negative word "ban" *inside*
      "bank" — a headline mentioning "global bank" with no actual negative content scored
      as if it had one. Fixed by switching to `\b...\b` word-boundary regex matching for
      every lexicon word; added a dedicated regression test
      (`test_score_headline_word_boundary_prevents_substring_false_positive`) asserting
      the correct score on exactly the headline that exposed the bug.
- [x] **`graph/nodes.py::news_analysis_node` rewritten** to fetch NSE filings (F1,
      existing) and Google News headlines (F4, new) **concurrently** per candidate (two
      `asyncio.gather` calls combined under one outer `asyncio.gather`, each candidate's
      calls individually `asyncio.wait_for(timeout=10.0)`-bounded — same defense-in-depth
      pattern as Step 2's filings fetch, now applied to the news fetch too so this doesn't
      reopen the 11-minute-run regression). Computes a combined `news_risk` per candidate:
      `DATA_UNAVAILABLE` only when *both* filings and news are unavailable, `ELEVATED` if
      either the filings keyword screen or the news sentiment label is negative, else
      `NORMAL`. `risk_agent_node` now reads this combined `news_risk` field directly
      (previously it read `filings_risk` under the `news_risk` key — a placeholder keyed
      to the old, narrower signal). `investment_report_node`'s `UNCERTAINTY` list gained a
      second line stating the sentiment label and its positive/negative headline counts,
      explicitly labelled "not an AI/NLP sentiment model" so the report never overclaims
      what produced that number.
- [x] **Route** `GET /market/stocks/{symbol}/news?name=` (`api/routes/market.py`) —
      standalone endpoint for the frontend News tab (separate from the research-graph
      path above, which computes its own combined signal internally for the pipeline).
      `name` (company name) gives a far more relevant search than the bare ticker;
      optional, falls back to the symbol alone. Returns
      `{symbol, status: OK|DATA_UNAVAILABLE, articles, sentiment}`.
- [x] **Frontend** — new **News** tab on the stock detail page
      (`app/stocks/[symbol]/page.tsx`, between Filings and Shareholding): a sentiment
      summary row (label + positive/negative counts, explicitly captioned "a
      keyword-lexicon score, not an AI sentiment model") above a clickable headline list
      (title, source, date, opens the article in a new tab), with the standard loading-
      skeleton / `DATA_UNAVAILABLE`-tile / error states matching every other tab. New
      types (`NewsArticle`, `NewsSentiment`, `StockNews`) in `lib/types.ts`, new
      `fetchStockNews` in `lib/api.ts`.
- [x] **Tests**: `tests/unit/market/test_news.py` (4 tests, 1 fixture
      `google_news_tcs.xml` — hand-written in the real RSS shape rather than scraped
      verbatim, so the sentiment test cases have fixed, documented expected scores
      instead of depending on whatever happens to be in the news that day).
      `tests/unit/test_sentiment.py` (8 tests, including the word-boundary regression
      above). No new test for `news_analysis_node`'s wiring itself — consistent with this
      codebase's existing convention of not independently unit-testing thin node-wiring
      logic in `graph/nodes.py` (see Step 1/2's notes on `sync.py`'s upsert loops having
      no unit tests either); covered instead by the existing `tests/graph/test_workflow.py`
      integration tests plus a manual live-backend curl check (see below).
      All green: `ruff check src tests` clean, `mypy` clean on every touched file, full
      `pytest -q` → **141 passed**, same 1 known pre-existing failure
      (`test_settings_defaults`).
      **Manually verified live**: `GET /market/stocks/TCS/news?name=Tata%20Consultancy%20Services`
      against the real running backend returned real, current Google News headlines with
      working links and source names.

Files touched this step:
- `src/investment_agent/market/news.py` (new)
- `src/investment_agent/research/sentiment.py` (new)
- `src/investment_agent/market/cache.py` (`CacheTTL.NEWS`)
- `src/investment_agent/graph/nodes.py` (`news_analysis_node` rewrite, `risk_agent_node`
  + `investment_report_node` updated to the combined `news_risk`/sentiment fields)
- `src/investment_agent/api/routes/market.py` (`GET /stocks/{symbol}/news`)
- `tests/unit/market/test_news.py`, `tests/unit/market/fixtures/google_news_tcs.xml` (new)
- `tests/unit/test_sentiment.py` (new, 8 tests)
- `frontend/src/lib/types.ts` (`NewsArticle`, `NewsSentiment`, `StockNews`)
- `frontend/src/lib/api.ts` (`fetchStockNews`)
- `frontend/src/app/stocks/[symbol]/page.tsx` (News tab)

### Step 5 — DONE

- [x] **`market/macro.py`** (new) — FRED's free, keyless CSV export
      (`fredgraph.csv?id=<series>`, confirmed live-reachable, unlike FRED's JSON API
      which needs a key). Two series, chosen for actually being current, not merely
      "an India series that exists" — several stale candidates checked during development
      (e.g. `INTDSRINM193N`, RBI's discount rate, last updated 2022) were deliberately
      left out:
      - `DEXINUS` — USD/INR spot rate, updated daily.
      - `CPALTT01INM659N` — India CPI YoY inflation.
      **Real bug caught before shipping**: the first draft assumed this series was a raw
      CPI index level (~150-160, like the separate `INDCPIALLMINMEI` series) and wrote
      code to re-derive YoY % in Python from two readings 12 months apart. The actual
      values (~2-5) were nowhere near an index level — checked FRED's own series
      description page (not just the series-ID naming convention) and confirmed it's
      labelled "Growth rate same period previous year," i.e. **already** the YoY rate
      computed upstream by FRED/OECD. Fixed by reading the latest value directly instead
      of re-deriving it. `cpi_inflation_yoy()`'s docstring records this so a future reader
      doesn't repeat the same wrong assumption from the series ID alone.
      Every field returns its own `data_date` so staleness is always visible — CPI in
      particular carries a real ~12-18 month reporting lag even from the official source.
      `CacheTTL.MACRO` (6h) added. `get_macro_snapshot()` degrades each field to its own
      `DATA_UNAVAILABLE` independently.
- [x] **Route** `GET /market/macro` (`api/routes/market.py`) → returns
      `{usd_inr: {...}, cpi_inflation_yoy: {...}}`, each with its own `status`.
- [x] **Frontend "Market Mood" strip** — new `components/MarketMoodStrip.tsx`: a
      horizontal strip of three chips on the home page
      (`app/page.tsx`, right under the greeting, above the quick-actions grid):
      - **Market mood** — "Risk-on"/"Risk-off"/"Flat", derived from nothing more than
        NIFTY's own existing day-change sign (already fetched via `/market/indices` —
        no new data source, no fabricated separate "mood score").
      - **USD/INR** — from the new macro endpoint.
      - **CPI inflation (YoY)** — from the new macro endpoint, with its `data_date`
        rendered inline (e.g. "2.95% as of Mar 2025") so the reporting lag is always
        visible rather than presented as if it were today's number.
      Each chip renders "Data unavailable" on its own rather than hiding or blanking when
      its field's `status` is `DATA_UNAVAILABLE`. New types (`MacroFieldUsdInr`,
      `MacroFieldCpi`, `MacroSnapshot`) in `lib/types.ts`, new `fetchMacroSnapshot` in
      `lib/api.ts`, fetched with a 10-minute `staleTime` (matches the data's own
      slow-changing nature — no point refetching every page focus).
- [x] **Tests**: `tests/unit/market/test_macro.py` (5 tests, 2 fixtures:
      `fred_dexinus.csv`, `fred_cpi_india.csv` — the latter includes a FRED `.`
      missing-value row to verify it's dropped rather than parsed as `0.0` or crashing).
      All green: `ruff check src tests` clean, `mypy` clean on every touched file, full
      `pytest -q` → **146 passed**, same 1 known pre-existing failure.
      **Manually verified live**: restarted the backend with the new code (a stale
      process from before this step's edits was still answering on port 8000 — same
      "kill by PID via `netstat`/`taskkill`" caveat noted in Workstream B's progress) and
      confirmed `GET /market/macro` returns real current USD/INR (₹95.81, dated
      2026-09-25) and real CPI inflation (2.95%, correctly dated 2025-03 — the lag is
      real and visible, not hidden).
      `pnpm lint`/`pnpm build` clean. Smoke-tested the home page and a stock detail page
      both return 200 from a fresh `pnpm dev` server; **could not visually confirm the
      strip's rendered appearance** — same no-browser-automation-tool caveat as
      Workstream B's frontend steps. The stock detail page's tab bar (including the new
      News tab) only appears after client-side data fetching completes, which curl's
      static HTML snapshot doesn't capture — confirmed this is pre-existing behavior (the
      page's own loading-gate), not something this step changed, by checking the SSR
      output shows the expected "Loading TCS" state.

Files touched this step:
- `src/investment_agent/market/macro.py` (new)
- `src/investment_agent/market/cache.py` (`CacheTTL.MACRO`)
- `src/investment_agent/api/routes/market.py` (`GET /macro`)
- `tests/unit/market/test_macro.py`, `tests/unit/market/fixtures/fred_dexinus.csv`,
  `tests/unit/market/fixtures/fred_cpi_india.csv` (new)
- `frontend/src/components/MarketMoodStrip.tsx` (new)
- `frontend/src/lib/types.ts` (`MacroFieldUsdInr`, `MacroFieldCpi`, `MacroSnapshot`)
- `frontend/src/lib/api.ts` (`fetchMacroSnapshot`)
- `frontend/src/app/page.tsx` (Market Mood strip wired in)

### Step 6 — superseded by Workstream B, no separate work done

Checked before starting fresh, per the plan above: Step 6's two asks (F5 — real mutual
fund data/search/detail, and a page to use it) are both already fully covered —
`GET /funds/search`/`GET /funds/{scheme_code}` (Workstream B, B3) and the "Mutual fund"/
"Suggest a mix" tabs on `/sip` (B5/B6) are strictly more than Step 6's own scope asked
for (real backtests, XIRR, tax estimates, risk-profile suggestions — not just a funds
listing page). Nothing left to reconcile; marking done by inspection rather than
re-building anything.

### Step 7 — DONE

- [x] **Gap 8 (portfolio concentration)** — `research/portfolio_insights.py` (new, pure
      Python): `build_concentration_report(holdings)` — reuses the pre-existing
      `portfolio/calculations.py::calculate_sector_exposure` (which had no caller outside
      the research graph's internal risk node until now) to compute sector exposure %,
      the single biggest holding's allocation %, a simple documented "100 minus the
      biggest sector's share" diversification score, and plain-language flags when
      either a sector (>30%) or a single holding (>20%) crosses its threshold — both
      thresholds are named module constants. This directly answers something the
      README's own "Layer B" description had been claiming since before this session
      ("evaluates... **existing portfolio concentration**...") without anything in the
      codebase actually computing it.
- [x] **Route** `GET /market/portfolio/concentration` (`api/routes/market.py`) — calls
      the existing `portfolio()` route function directly to reuse its live-holdings
      logic, then runs the report over `holdings`.
- [x] **Frontend `/portfolio` page** (new) — sector-exposure stacked bar + breakdown
      list, a `ScoreRing` (reused as-is) showing the diversification score, and a
      holdings table (symbol → stock page, allocation %, value, P&L). Added to
      `AppNav.tsx`'s section nav. Shows an honest "No broker connected" / "No holdings
      yet" empty state rather than a blank page when there's nothing to show.
      **Not reconciled this step** (noted, not silently skipped): the pre-existing
      `BrokerVaultCard.tsx` (home page) has its own hardcoded "Safeguard caps" strip
      ("Single stock max 15%", "Sector max 25%") that predates this session and isn't
      wired to any computed value — different numbers from this step's own 20%/30%
      thresholds. Left alone rather than silently changed, since touching copy on an
      already-shipped, unrelated component wasn't asked for; flagging here so a future
      session doesn't read the two different numbers as a bug introduced by this step.
- [x] **Tests**: `tests/unit/test_portfolio_insights.py` (4 tests: empty portfolio,
      well-diversified-has-no-flags, sector-over-threshold, single-holding-over-threshold
      — each hand-verified against the chosen input numbers).
      All green: `ruff check src tests` clean, `mypy` clean, full `pytest -q` passing
      (see Step 8's combined total below), `pnpm lint`/`pnpm build` clean.
      **Manually verified live**: `GET /market/portfolio/concentration` against the real
      running backend returns the correct empty-portfolio shape (no broker connected in
      this environment).

Files touched this step:
- `src/investment_agent/research/portfolio_insights.py` (new)
- `src/investment_agent/api/routes/market.py` (`GET /portfolio/concentration`)
- `tests/unit/test_portfolio_insights.py` (new, 4 tests)
- `frontend/src/app/portfolio/page.tsx` (new)
- `frontend/src/components/AppNav.tsx` (Portfolio nav link)

### Step 8 — DONE

- [x] **F8 (alerts)** — `research/alerts.py` (new, pure Python):
      `generate_portfolio_alerts(holdings)` — per-holding drawdown alerts (≤-15% from
      average buy price, `DRAWDOWN`/`WARNING`) and single-holding concentration alerts
      (reuses Step 7's 20% threshold, `CONCENTRATION`/`INFO`), plus Step 7's
      portfolio-wide sector flag folded in as a `SECTOR_CONCENTRATION` alert (deduplicated
      against an existing per-holding concentration alert so the same root cause doesn't
      show twice under two different wordings). No LLM call, no day-trading "buy now"/
      "sell now" instruction — every alert states the exact numbers behind it.
      Route: `GET /market/portfolio/alerts`.
- [x] **F9 (compare)** — `GET /research/compare?symbols=A,B,C&exchange=` (`api/routes/
      research.py`) — runs Step 3's `build_stock_score` concurrently (bounded
      `asyncio.wait_for(20s)` per symbol, one slow/failing symbol degrades to its own
      `DATA_UNAVAILABLE` row rather than failing the whole comparison) for up to 5
      symbols. **Registered before the existing `GET /{asset_id}` catch-all route** —
      that single-path-segment route would otherwise have silently swallowed
      `GET /research/compare` as if `"compare"` were an asset_id, since FastAPI matches
      routes in registration order. Caught by reasoning through the route table before
      wiring it in, not by a failing test.
      Frontend: new `/compare` page — add up to 5 symbols as removable pills, a
      side-by-side table (one `ScoreRing` row for Overall, color-coded numeric rows for
      Quality/Valuation/Momentum/Risk, reusing the same ≥70/40 green/amber/red thresholds
      `ScoreRing` itself uses). Added to `AppNav.tsx`.
- [x] **Gap 7 (outcome scoring)** — the real finding this step: `PredictionLog` (from a
      prior session, predating this workstream) had `outcome_status`/`evaluation_notes`/
      `evaluation_due_date` columns and `graph/nodes.py::recommendation_logger_node` was
      already writing a row every research run — but it **never set `evaluation_due_date`
      and never recorded the price at prediction time**, so there was no way for anything
      to later check "did this call turn out to be right," even in principle. Fixed both
      gaps in `recommendation_logger_node`: now stores `entry_price` (the selected
      candidate's price at prediction time) and `decision` inside `expected_conditions`,
      and sets `evaluation_due_date = now + EVALUATION_HORIZON_DAYS` (90, a module
      constant in the new `research/outcome_scoring.py`).
      `research/outcome_scoring.py::classify_outcome(decision, entry_price, current_price)`
      (pure) — `OPPORTUNITY` scores `CORRECT`/`INCORRECT` by price direction (flat counts
      as `INCORRECT`, since "worth watching" implied some upside); `NO_ACTION` scores
      `NOT_APPLICABLE` (no directional call was made, never fabricated as right or
      wrong); a missing price or an unrecognized decision value scores `INCONCLUSIVE`,
      never silently skipped or guessed. `evaluate_due_predictions()` (I/O wrapper):
      queries every `PredictionLog` row past its `evaluation_due_date` with no
      `outcome_status` yet, fetches each one's current live price
      (`market/board.py::quote_for_symbol`), classifies, writes `outcome_status`/
      `evaluation_notes` back — one symbol's price-fetch failure classifies that row
      `INCONCLUSIVE` and moves on rather than aborting the whole batch.
      Routes: `POST /research/predictions/evaluate` (trigger scoring, same
      manually-triggered pattern as `POST /market/refresh`) and `GET /research/predictions`
      (list, newest first — exists mainly to verify this is actually running, not a
      polished tracked-record UI feature; no frontend page built for it this step, since
      the original spec's own F/Gap split treats "gap" items as backend-only, matching
      every prior step's Gap items 1/2/4/5/6/8 which also shipped with no dedicated UI).
      Both new routes registered before the `/{asset_id}` catch-all for the same reason
      as `/compare` above (`/predictions` is a single path segment too).
- [x] **Tests**: `tests/unit/test_alerts.py` (5 tests), `tests/unit/test_outcome_scoring.py`
      (7 tests covering every `classify_outcome` branch with hand-picked prices). No DB-
      level test for `evaluate_due_predictions()` itself — consistent with this
      codebase's established convention (see Step 1/B1's notes on `sync.py`'s upsert
      loops) of not unit-testing thin DB-session wrapper code that needs a real Postgres
      connection; its pure classification core is what's actually tested.
      All green: `ruff check src tests` clean, `mypy` clean on every touched file
      (including `graph/nodes.py`, re-checked after the logger changes), full
      `pytest -q` → **162 passed**, same 1 known pre-existing failure
      (`test_settings_defaults`).
      **Manually verified live** against the real running backend: `GET
      /market/portfolio/alerts` (empty, no broker connected — correct), `GET
      /research/compare?symbols=TCS` (real computed score card returned),
      `GET /research/predictions` (listed real rows from earlier sessions' research runs,
      confirming `entry_price`/`evaluation_due_date` are now populated for new rows and
      correctly `null` for old ones written before this fix), and
      `POST /research/predictions/evaluate` (`{"evaluated_count": 0, "evaluated": []}` —
      correct, since the new 90-day due dates haven't arrived yet).

Files touched this step:
- `src/investment_agent/research/alerts.py` (new)
- `src/investment_agent/research/outcome_scoring.py` (new)
- `src/investment_agent/graph/nodes.py` (`recommendation_logger_node`: `entry_price` +
  `evaluation_due_date` now recorded, `EVALUATION_HORIZON_DAYS` import)
- `src/investment_agent/api/routes/market.py` (`GET /portfolio/alerts`)
- `src/investment_agent/api/routes/research.py` (`GET /compare`, `GET /predictions`,
  `POST /predictions/evaluate`, all registered before the `/{asset_id}` catch-all)
- `tests/unit/test_alerts.py` (new, 5 tests), `tests/unit/test_outcome_scoring.py`
  (new, 7 tests)
- `frontend/src/app/compare/page.tsx` (new)
- `frontend/src/components/AppNav.tsx` (Compare nav link)
- `frontend/src/lib/types.ts` (`ConcentrationReport`, `PortfolioAlert`, `CompareResult`)
- `frontend/src/lib/api.ts` (`fetchPortfolioConcentration`, `fetchPortfolioAlerts`,
  `compareStocks`)

### Currently in progress

**Workstream A is now fully complete — Steps 1 through 8 all DONE** (Step 6 by
inspection/supersession, the rest by direct implementation). Combined with Workstream B
(B1-B7, also fully complete), **both workstreams from this file's original two pasted
specs are done.** Backend (`ruff`/`mypy`/`pytest`, 162 passed / 1 known pre-existing
failure) and frontend (`pnpm lint`/`pnpm build`) are both green as of this step, and
every new endpoint across both workstreams has been manually verified against the real
running backend at least once (not just unit-tested in isolation).

**Known remaining gaps, intentionally not addressed (not asked for, flagging for
visibility rather than silently leaving undocumented):**
- `BrokerVaultCard.tsx`'s hardcoded "Safeguard caps" strip (15%/25%) is still
  disconnected from Step 7's real computed thresholds (20%/30%) — see Step 7's note.
- No expense-ratio/TER data source exists for mutual funds (Workstream B, B3/B4) —
  `expense_ratio_drag` has no real input to run on via any route.
- NSE/BSE's own endpoints have never been verified against the real live API from this
  sandbox (Akamai-blocked here) — only respx-mocked tests exist for `market/nse.py`.
- Gap 7's outcome scoring has no frontend page — by design this step (see Step 8), but
  worth building a simple "track record" view if the user wants visibility into it later.
- `/research/compare` and `/market/portfolio/{concentration,alerts}` have no dedicated
  unit tests at the route-wiring level (only their underlying pure functions are
  tested) — consistent with this codebase's convention elsewhere, but noting it since
  this file has flagged the same convention choice at every step it came up.

**Next action**: none scoped — both workstreams are complete. Future work would be a
new ask from the user, not a continuation of either pasted spec.

---

## Workstream B — SIP calculator rebuild (real mutual funds, not just ETFs)

Source: the pasted spec titled "Rebuild the SIP calculator so it works on real mutual
funds." Today `research/sip.py` only builds a 4-mix ETF allocator (NIFTYBEES/JUNIORBEES/
GOLDBEES/BANKBEES/ITBEES) with a fixed 12% projection and a one-word LLM style classifier —
no real funds, no search, no backtest, no XIRR, no tax/expense modeling.

Delivery order (one commit each):

- [x] **B1** — DONE, see below.
- [x] **B2** — DONE, see below.
- [x] **B3** — DONE, see below.
- [x] **B4** — DONE, see below.
- [x] **B5** — DONE, see below.
- [x] **B6** — DONE, see below.
- [x] **B7** — DONE, see below.

**Tests required throughout:** recorded-fixture unit tests for AMFI parsing and mfapi
responses under `tests/unit/market/` (reuse the Workstream-A-Step-1 pattern — see above);
unit tests for XIRR/backtest/drawdown/projection/step-up/tax/expense-drag against
hand-computed values under `tests/unit/portfolio/`; API tests per route including
`DATA_UNAVAILABLE` paths. Run backend checks + `cd frontend && pnpm lint && pnpm build`
before each commit.

**Hard rules to keep front of mind while implementing this workstream:**
- Python computes every number; the LLM may only narrate numbers it's given, never invent
  or adjust them. Any LLM call needs a deterministic fallback if it fails/times out.
- Every figure shown to the user is backed by an `Evidence` object with source, URL, and
  data date (`research/evidence.py`).
- Missing data renders as `DATA_UNAVAILABLE` (frontend: a muted "Data unavailable" tile) —
  never silently shown as `₹0` or blank.
- Guidance only — no trade-order placement, no day-trading features.

### B1 — DONE (migration applied)

- [x] **Migration** `alembic/versions/003_mutual_fund_scheme.py` — new `mutual_fund_schemes`
      table. Deliberately uses `scheme_code` as the primary key (not the usual
      `TimestampMixin` surrogate `id` pattern every other table in this codebase uses) —
      the spec's own column list asks for `scheme_code (PK)` explicitly, and AMFI scheme
      codes are already a stable unique identifier, so a surrogate key would be redundant.
      Model: `db/models/market.py::MutualFundScheme`.
      **Migration applied** — ran `uv run alembic upgrade head` with the user's explicit
      go-ahead. Confirmed via `alembic current`: `003_mutual_fund_scheme (head)`. The
      `mutual_fund_schemes` table now exists in the real database; it's just empty until
      the sync job below is actually triggered (e.g. `POST /market/refresh`).
- [x] **AMFI parsing extended** (`market/amfi.py`) — `parse_nav_file` previously discarded
      every non-scheme line (fund house names, category headers) as unparseable noise. It
      now tracks both as it scans (a fund house line resets the pending category; a
      category-header line — detected via `"schemes("` in the text, matching AMFI's actual
      format — updates it) so every scheme row carries accurate `fund_house`/`category`
      context. Added three **deterministic** (no LLM) classifiers consumed by every scheme
      row: `classify_plan` (direct/regular), `classify_option` (growth/idcw),
      `classify_sebi_group` (large/mid/small/flexi/elss/index/debt/hybrid/gold/other, from
      category + name text, with gold/silver checked *before* the generic "index"/"etf"
      catch-all).
      **Bug the tests caught:** `classify_sebi_group` initially checked for "index"/"etf"
      before "gold"/"silver" — a Gold ETF's name contains "ETF", so it was being
      misclassified as "index" instead of "gold". Reordered gold/silver ahead of the
      index/etf check; regression test added (`test_classify_sebi_group_order_of_precedence`).
- [x] **Sync job** (`market/sync.py`) — new `sync_mutual_fund_schemes(settings)`: downloads
      the full AMFI NAVAll.txt (every scheme, not filtered to `AMFI_SCHEME_CODES` like the
      existing NAV-record sync is), classifies each row, and upserts into
      `mutual_fund_schemes` keyed by `scheme_code`. Wired into `refresh_market_data()`
      alongside Step 2's `sync_fundamentals` — **before** the `indstocks_configured` gate,
      so it runs on `POST /market/refresh` regardless of whether a broker is connected
      (free/keyless data shouldn't need a broker). Added `mutual_fund_schemes_synced` to
      the refresh summary.
      **Not unit-tested at the DB-write level** — consistent with this codebase's existing
      convention: the pre-existing `instruments`/`daily_bars`/`nav_records` upsert loops in
      this same file have no unit tests either (they need a real Postgres connection,
      which this test suite doesn't set up). Coverage here is on the pure parsing/
      classification logic in `test_amfi.py`, which is where an actual bug was in fact
      found and fixed (see above) — the thin upsert wrapper mirrors an already-established,
      already-unverified-at-this-level pattern rather than inventing a new one.
- [x] **SourceType confirmation** — `MFAPI` and `AMFI` both already exist in
      `research/evidence.py`'s `SourceType` enum (MFAPI added in Workstream A Step 1; AMFI
      predates this session). No code change needed for this part of B1.
- [x] Lint/typecheck/tests: `ruff check src tests` clean; `mypy` on every touched file
      clean except the same pre-existing errors (now at shifted line numbers, nothing
      new — two *new*-looking errors from an untyped `dict[str, object]` value were fixed
      with an explicit `cast(float, ...)` rather than left as "more of the same"); full
      `pytest` 75 passed (74 + the 1 known pre-existing `test_settings_defaults` failure).

Files touched this step:
- `alembic/versions/003_mutual_fund_scheme.py` (new)
- `src/investment_agent/db/models/market.py` (`MutualFundScheme` model)
- `src/investment_agent/market/amfi.py` (fund_house/category tracking, 3 new classifiers)
- `src/investment_agent/market/sync.py` (`sync_mutual_fund_schemes`, wired into
  `refresh_market_data`, `cast` import)
- `tests/unit/market/test_amfi.py` (new, 4 tests)

### B2 — DONE

**mfapi.in is fully reachable from this environment** (unlike NSE/BSE in Step 2) —
confirmed with a real live call during development, and both test fixtures below were
recorded from that live call, trimmed, not reconstructed from docs. High confidence here,
no live-verification caveat needed.

- [x] **`market/mfapi.py`** (new) — `search(query)` (`GET /mf/search?q=`) and
      `fetch_nav_history(scheme_code)` (`GET /mf/{scheme_code}`, full history + meta:
      fund_house, scheme_category, isin_growth). Both: httpx with a short retry/backoff
      (`_get_with_retry`, 1 initial attempt + 2 retries at 0.5s/1.5s on 5xx or a network
      error; 4xx returns immediately, never retried), cached via Step 1's `market/cache.py`
      (`CacheTTL.MF_SEARCH`=1h, `CacheTTL.MF_NAV_HISTORY`=12h — both new enum members),
      degrade to `[]`/`None` on any failure rather than raising. mfapi.in dates are
      `dd-mm-yyyy`; normalized to ISO (`yyyy-mm-dd`) on the way in so nothing downstream
      has to know mfapi's native format. `nav_history` is kept **newest-first**, matching
      mfapi.in's own ordering — `fund_metrics.py` depends on that ordering and documents it.
- [x] **`portfolio/fund_metrics.py`** (new, pure Python, no I/O):
      - `calculate_xirr(cash_flows)` — genuine Newton-Raphson IRR solver on dated
        (date, amount) cash flows, not an approximation. Returns `None` on <2 flows, all
        same-sign flows, or non-convergence within 100 iterations.
      - `NavSeries` — small internal helper: reverses mfapi's newest-first history into
        chronological order once, with `bisect`-based "nearest NAV on or before this date"
        lookups (SIP installment dates almost never land exactly on a published NAV date).
      - `trailing_cagr(nav_history, years)` — 1/3/5/10y all just call this with a
        different `years`; `None` if the history doesn't go back far enough.
      - `sip_backtest(nav_history, monthly_amount, start_date, step_up_pct=0.0)` — real
        month-by-month simulation against actual historical NAVs (not a formula): units
        bought each month, invested total, current value, and XIRR via the solver above.
        Step-up applies once every 12 installments, not every month.
      - `rolling_return_extremes(nav_history, window_years=3.0)` — best/worst CAGR from
        any entry/exit point in the history, stepping ~monthly (not daily — a screening
        metric, not a precise backtest; documented as such).
      - `project_sip(monthly, years, annual_return_pct, step_up_pct, inflation_pct)` —
        nominal + inflation-adjusted forward projection; step-up handled by compounding
        each year's contribution forward to the full horizon at the assumed rate.
      - `ltcg_stcg_estimate(gains, holding_period_years, is_equity=True)` — ₹1.25L LTCG
        exemption, 12.5% LTCG / 20% STCG, rates as module-level constants
        (`LTCG_EXEMPTION_INR`, `LTCG_RATE_PCT`, `STCG_RATE_PCT`) — "rates in config" per the
        spec, meaning a single clearly-labeled place to edit, not a new Settings/env-var
        plumbing exercise for tax-law constants that aren't deployment secrets.
        **Deliberately refuses to estimate for `is_equity=False`** (debt funds are taxed at
        the investor's slab rate, which this function has no way to know) rather than
        silently applying the wrong rate — returns `DATA_UNAVAILABLE`.
      - `expense_ratio_drag(monthly, years, annual_return_pct, ter_regular_pct, ter_direct_pct)`
        — models TER as a direct drag on the assumed return, reusing the existing
        `calculate_sip_future_value`.
      - `calculate_max_drawdown` and `calculate_annualized_volatility_pct` were already
        built in Step 3 (`portfolio/calculations.py`) and are reused as-is for a fund's NAV
        series — no duplicate implementation needed here.
- [x] **Tests**: `tests/unit/market/test_mfapi.py` (5 tests, 2 recorded fixtures:
      `mfapi_search_hdfc.json`, `mfapi_scheme_119598.json`). `tests/unit/portfolio/test_fund_metrics.py`
      (20 tests, new `tests/unit/portfolio/` directory per the spec) — every test asserts
      against a **hand-computed expected value** (e.g. the flat-NAV SIP test asserts
      `xirr_pct ≈ 0` because invested exactly equals current value regardless of timing;
      the LTCG test asserts `tax == 9375.0` from `(200000 - 125000) * 0.125` worked by
      hand), not just "it ran without crashing." All 20 passed on the first run — the math
      held up under hand-verification.
      All green: `ruff check src tests`, `mypy` on every touched file, full `pytest`
      (100 passed, same 1 pre-existing failure), no frontend changes this step.

Files touched this step:
- `src/investment_agent/market/mfapi.py` (new)
- `src/investment_agent/market/cache.py` (`CacheTTL.MF_SEARCH`, `CacheTTL.MF_NAV_HISTORY`)
- `src/investment_agent/portfolio/fund_metrics.py` (new)
- `tests/unit/market/test_mfapi.py`, `tests/unit/market/fixtures/mfapi_search_hdfc.json`,
  `tests/unit/market/fixtures/mfapi_scheme_119598.json` (new)
- `tests/unit/portfolio/test_fund_metrics.py` (new, 20 tests; also created the
  `tests/unit/portfolio/` directory)

### B3 — DONE

- [x] **New route file** `api/routes/funds.py` (`/funds` prefix, registered in
      `api/routes/__init__.py` and `main.py`) rather than folding into `market.py`/
      `research.py` — the spec explicitly groups these under their own `/funds` namespace.
      - `GET /funds/search?q=&category=&plan=&limit=` — queries B1's `mutual_fund_schemes`
        table first (name `ILIKE` or exact scheme-code match, optional `sebi_group`/`plan`
        filters) since it carries plan/option/SEBI-group classification mfapi.in's own
        search doesn't. Falls back to `mfapi.search()` (unclassified results) when the DB
        has no match — covers both "not synced yet" and genuinely-obscure-scheme cases.
        Database errors return 503, not a 500 crash.
      - `GET /funds/{scheme_code}` — facts from the DB row if present (else reconstructed
        from mfapi's own meta, with classification fields `None`), trailing 1/3/5/10y
        returns via B2's `trailing_cagr`, risk via Step 3's `calculate_max_drawdown`/
        `calculate_annualized_volatility_pct` (reused as-is — a fund NAV series is just
        another price series to those functions), and 3y rolling-return extremes via B2's
        `rolling_return_extremes`. Returns `{"status": "DATA_UNAVAILABLE", ...}` (not an
        HTTP error) when mfapi has no history for the code, consistent with this project's
        "missing data is a normal response shape, not an exception" convention.
      - `POST /funds/sip/backtest` — thin wrapper over B2's `sip_backtest`. When
        `start_date` is omitted, defaults to 5 years back from the latest NAV date, clamped
        to the earliest date the series actually has (so a young fund doesn't 404/error on
        an impossible backtest window).
      - `POST /funds/sip/project` — thin wrapper over B2's `project_sip`. **Deliberate
        deviation from the spec's literal field list**: the spec names
        `{monthly, years, step_up_pct, inflation_pct}` for this route, but `project_sip`
        requires an assumed `annual_return_pct` to run at all — added as an optional field
        defaulting to 12.0 (documented inline in `SipProjectRequest`) rather than silently
        picking an undocumented constant or breaking the function contract.
      - **`POST /funds/sip/suggest` intentionally NOT added** — the spec lists it among
        this step's routes, but the logic it needs (`research.sip.suggest_mix`, deterministic
        category-weight-by-risk-profile selection) is explicitly a B4 deliverable. Adding a
        route now would mean either duplicating that logic early or shipping a stub that
        gets thrown away; B4 adds the route alongside `suggest_mix` itself. Called out
        explicitly in the module docstring so this isn't mistaken for an oversight.
      - Pydantic validation on both POST bodies: `monthly` 100..1,000,000, `years` 1..40,
        `step_up_pct`/`inflation_pct` 0..25 (`Field(ge=..., le=...)`).
- [x] **Tests**: `tests/unit/api/test_funds_routes.py` (new, new `tests/unit/api/`
      directory, 15 tests) — route functions called directly (FastAPI handlers are plain
      async functions) with `async_session_factory`/`fetch_nav_history`/`mfapi_search`
      monkeypatched on the `funds` module, matching the existing `test_stock_score.py`
      wiring-test pattern. Covers: DB-hit vs. mfapi-fallback search, 503 on DB error,
      `DATA_UNAVAILABLE` vs. OK fund-detail shapes (both DB-backed and mfapi-only facts),
      default-start-date clamping in backtest, 502 on missing NAV history, projection's
      assumption note, and Pydantic range-validation rejections for both POST bodies.
      All green: `ruff check src tests` clean (one import-sort auto-fix applied), `mypy`
      clean on the new file, full `pytest -q` → **115 passed**, 1 known pre-existing
      failure (`test_settings_defaults`), ~25s.

Files touched this step:
- `src/investment_agent/api/routes/funds.py` (new)
- `src/investment_agent/api/routes/__init__.py` (`funds_router` export)
- `src/investment_agent/main.py` (`app.include_router(funds_router)`)
- `tests/unit/api/test_funds_routes.py` (new, 15 tests; also created the
  `tests/unit/api/` directory)

### B4 — DONE

- [x] **`research/sip.py` rewritten.** `build_sip` renamed to `build_etf_sip` (same
      signature/response shape, `"mode": "etf"` field added) — `_ai_style_pick` (the
      one-word LLM style classifier) **deleted entirely**, per the spec's explicit call-out
      that it's no longer worth keeping. Style selection is now purely the deterministic
      rule that already existed (requested style, downgraded from small→flexi under a
      5-year horizon) — no model round-trip, no behavior change a user would notice beyond
      the note text being honestly reworded ("bought via your broker... not a mutual-fund
      recommendation" instead of implying AI judgment went into the pick).
      `api/routes/research.py::research_sip` and `research/chat.py` (the only two callers)
      updated to call `build_etf_sip`; `POST /research/sip` request/response shape is
      unchanged.
      **mypy/ruff note**: no new errors from this rename; one ruff import-sort auto-fix
      applied to the new file.
- [x] **`build_fund_sip(scheme_code, monthly, years, step_up_pct=0, inflation_pct=0)`**
      (new) — fetches NAV history (`market/mfapi.py`), backtests the SIP over the last 5
      years of real history (`fund_metrics.sip_backtest`), projects it forward at the
      fund's **own** trailing 5y CAGR (falling back to 3y, then a conservative flat 10% —
      never a single global constant across every fund category), estimates LTCG/STCG on
      the backtest's realized gain (`ltcg_stcg_estimate`, equity-vs-debt decided from the
      scheme's category text), then an LLM CHEAP-tier call narrates the finished numbers
      with a deterministic fallback (`_fallback_fund_explanation`) if that call fails —
      same invariant as `research/stock_score.py::_explain`. `DATA_UNAVAILABLE` status
      (not an exception) when NAV history can't be fetched.
      **Expense-ratio drag was spec'd for this builder but is NOT included**: AMFI's
      scheme master (`market/amfi.py`) carries no TER field, and there is no free TER
      source wired into this project, so `expense_ratio_drag` (built in B2) currently has
      no real input to run on here — using a guessed/typical TER would violate the
      no-fabricated-numbers rule. Left for a future step if a TER source is added.
- [x] **`suggest_mix(monthly, horizon_years, risk_profile)`** (new) — deterministic
      category weights by horizon/risk via a lookup table (`_RISK_WEIGHTS`: conservative/
      moderate/aggressive, each a dict of SEBI-group → weight %), with a horizon guard
      (<3 years always forces conservative weights, mirroring the ETF mix's small→flexi
      downgrade). For each weighted category, queries B1's `mutual_fund_schemes` table for
      Direct+Growth candidates (`_candidates_for_group`, capped pool of 6 per category),
      fetches each candidate's NAV history concurrently (`asyncio.gather` +
      `asyncio.wait_for(8s)` per candidate — bounded the same way Step 2's NSE filings
      fetch is, so one slow/dead candidate can't stall the whole suggestion), and picks the
      best by trailing 5y return (falling back to 3y), preferring a fund with a full 5y
      track record over one with a merely higher 3y number.
      **"Lowest expense ratio" from the spec's objective-rules list is NOT used as a
      selection criterion**, for the same reason as above (no TER data source) — documented
      in the function's docstring and in the response's `note` field so this reads as a
      deliberate, disclosed limitation rather than a silently-dropped requirement. A
      category with zero synced candidates (e.g. before `POST /market/refresh` has ever
      run) degrades to a `"status": "DATA_UNAVAILABLE"` sleeve rather than failing the
      whole suggestion.
      LLM CHEAP-tier narration + deterministic fallback (`_fallback_suggestion_explanation`),
      same pattern as `build_fund_sip`.
- [x] **`api/routes/funds.py`** — added the two routes this builder pair backs:
      `POST /funds/sip/fund` (wraps `build_fund_sip`) and `POST /funds/sip/suggest`
      (wraps `suggest_mix`, deferred from B3 — see that section). Both with the same
      Pydantic range validation convention as B3 (`monthly` 100..1,000,000, `years`/
      `horizon_years` 1..40, `step_up_pct`/`inflation_pct` 0..25).
- [x] **Tests**: `tests/unit/test_sip.py` (new, 9 tests) — `build_etf_sip`'s deterministic
      style rules (requested style kept, small→flexi downgrade under 5y, unknown style
      defaults to flexi), `build_fund_sip`'s `DATA_UNAVAILABLE` path, a full assembled
      response (equity fund → tax estimate is never `DATA_UNAVAILABLE`), and the debt-fund
      case (tax estimate **is** `DATA_UNAVAILABLE`, confirming the equity/debt branch is
      wired correctly); `suggest_mix`'s horizon override (horizon<3 forces conservative
      weights even on an "aggressive" request), the all-`DATA_UNAVAILABLE`-sleeves path
      when the candidate DB is empty, and the unknown-risk-profile→moderate default. All
      I/O (`_live_price`, `fetch_nav_history`, `_candidates_for_group`, `_best_pick`, both
      `_explain_*` LLM calls) monkeypatched — matches the project's established
      wiring-test convention (`test_stock_score.py`).
      All green: `ruff check src tests` clean, `mypy` clean on every touched file, full
      `pytest -q` → **124 passed**, same 1 known pre-existing failure
      (`test_settings_defaults`), ~23s.

Files touched this step:
- `src/investment_agent/research/sip.py` (rewritten: `build_etf_sip` replaces `build_sip`,
  `_ai_style_pick` deleted, `build_fund_sip` + `suggest_mix` added)
- `src/investment_agent/api/routes/research.py` (`build_etf_sip` import/call)
- `src/investment_agent/research/chat.py` (`build_etf_sip` import/call)
- `src/investment_agent/api/routes/funds.py` (`POST /funds/sip/fund`,
  `POST /funds/sip/suggest`)
- `tests/unit/test_sip.py` (new, 9 tests)

### B5 — DONE

- [x] **Mode toggle** added to `app/sip/page.tsx` — three `nav-pill` buttons ([Mutual
      fund] [Suggest a mix] [ETF mix]), `useState<Mode>` defaulting to `"fund"`. The
      pre-existing ETF calculator body (inputs, projection card, mix result section) was
      left as-is functionally and wrapped in `mode === "etf" && (...)`, not rewritten —
      only its header copy and the `plan.style !== plan.requested_style` badge changed
      (see below). `"suggest"` renders an honest placeholder card (no fake data, says the
      feature is "coming to this tab next" and points at the other two tabs) since
      `suggest_mix`'s UI is explicitly B6's job.
      **Mislabel fixed while here**: that badge used to read "✨ AI switched you to {style}
      cap," left over from B4's deletion of `_ai_style_pick` — the style change is now
      (and was already, post-B4) purely the deterministic small→flexi-under-5y rule, so
      the AI/sparkles framing was actively false. Changed to "Adjusted to {style} cap for
      this horizon." This is effectively doing a slice of B6's "ETF mode relabel" early
      because leaving a disproved AI-attribution claim live in the UI for another step
      would violate the no-overclaiming-AI-involvement rule this project holds elsewhere.
- [x] **`components/FundSearch.tsx`** (new) — debounced (350ms) combobox over
      `GET /funds/search`. Handles both response shapes (DB-backed `FundSummary` with
      fund_house/plan/option, or the unclassified mfapi.in fallback `{scheme_code,
      scheme_name}`) via a type guard, shows an inline "no matching funds — may not be
      synced yet" hint rather than a bare empty dropdown, and surfaces fetch errors
      inline. Selecting a result calls back with `{scheme_code, name}` and fills the
      input with the chosen name (closes the dropdown).
      **Lint catch**: the first draft called `setResults([])`/`setOpen(false)`
      synchronously inside a `useEffect` body for the short-query case, which
      `eslint-plugin-react-hooks`'s `set-state-in-effect` rule flags (cascading-render
      risk) — moved that specific clear into the `onChange` handler directly, leaving the
      effect to own only the actual debounced fetch.
- [x] **`components/FundSipPanel.tsx`** (new) — single-fund analysis panel: `FundSearch`
      for scheme selection, sliders for monthly amount / horizon years / annual step-up
      (same slider styling convention as the existing ETF calculator), and an "Analyze
      this fund" button that fires `GET /funds/{scheme_code}` (facts/trailing-returns/
      risk), `POST /funds/sip/backtest`, and three parallel `POST /funds/sip/project`
      calls (8/10/12% scenarios) via `Promise.all`. Renders three cards: fund facts (1y/
      3y/5y/10y trailing returns, max drawdown, annualized volatility, source link),
      historical backtest (invested/current value/XIRR, with a plain-language framing —
      "had you started this SIP on {date}, this is what really happened"), and forward
      projection (three rate rows, each carrying the backend's own "assumption, not a
      forecast" note rather than a hardcoded client-side string).
      **Scope note**: did not reuse `PriceChart.tsx`'s candle-rendering SVG for an
      invested-vs-value line as the spec suggested — `PriceChart` is typed specifically
      around `Candle[]` (OHLC+ts) and the backtest result here is a single invested/
      current-value pair, not a price series; building a fake 2-point "chart" would add
      complexity without showing anything a bar comparison doesn't already show clearly.
      Used plain labeled rows instead, consistent with how the existing ETF mix section
      presents its invested-vs-gains split (a progress bar + two labeled rows, not a
      chart). Can revisit with a real chart if/when the backtest route starts returning
      a value-over-time series instead of just start/end totals.
- [x] **`lib/types.ts`**: `FundSummary`, `FundSearchResult`, `FundDetail`,
      `FundSipBacktestResult`, `FundSipProjectResult`. **`lib/api.ts`**: `searchFunds`,
      `fetchFundDetail`, `fundSipBacktest`, `fundSipProject` (all via the existing
      `readJson`/`postJson` helpers, consistent with every other API function in the
      file).
- [x] **Manually verified**: started the real backend (`uvicorn`) and frontend
      (`pnpm dev`) together. Confirmed live against the real (unsynced)
      `mutual_fund_schemes` table: `GET /funds/search?q=sbi` correctly falls back to
      mfapi.in's own search (DB empty); `GET /funds/119598`, and
      `POST /funds/sip/backtest` with that scheme code, both return real computed numbers
      (trailing returns, -37.08% max drawdown, 7.25% backtest XIRR on a real SBI Large
      Cap Fund NAV series) end to end from a live curl against the running server.
      `curl`'d the rendered `/sip` page HTML and confirmed all three mode labels render
      (SSR'd before hydration). **Caveat**: no visual/interactive browser check was done
      (no browser-automation tool available in this session) — the dropdown-select→
      analyze→cards-render click path itself was not visually exercised, only confirmed
      via direct API calls plus the component code review. Flagging this explicitly
      rather than claiming a full UI walkthrough happened.
      `pnpm lint` clean (after the effect fix above), `pnpm build` clean (TypeScript +
      static generation, 7s).

Files touched this step:
- `frontend/src/app/sip/page.tsx` (mode toggle, ETF body gated behind `mode === "etf"`,
  header copy, AI-mislabel fix)
- `frontend/src/components/FundSearch.tsx` (new)
- `frontend/src/components/FundSipPanel.tsx` (new)
- `frontend/src/lib/types.ts` (fund types)
- `frontend/src/lib/api.ts` (fund API functions)

### B6 — DONE

- [x] **`components/SuggestMixPanel.tsx`** (new) — amount/horizon-years sliders (same
      convention as the other two panels) + a risk-profile pill selector (conservative/
      moderate/aggressive), with an inline note when the horizon-under-3-years override
      will apply regardless of the selected profile (mirrors `suggest_mix`'s backend
      guard, stated honestly rather than silently surprising the user with a different
      mix than what they picked). "Suggest a mix" calls `POST /funds/sip/suggest` and
      renders: a stacked weight bar (one segment per SEBI category, from a small
      category→color map), a per-category fund table where each row shows its `status`
      honestly — a `DATA_UNAVAILABLE` row renders an amber "not enough synced data for
      this category yet" chip with a warning icon rather than being hidden or showing a
      blank/zero — and the response's `explanation` plus its `note` about expense ratio
      not being used as a selection criterion.
      Wired into `app/sip/page.tsx`'s `mode === "suggest"` branch, replacing B5's
      placeholder card.
- [x] **ETF mode relabel finished.** B5 already fixed the one actively-false "AI
      switched you to {style} cap" badge. This step adds the persistent clarifying note
      the spec asked for ("ETF SIP via broker" framing): a line above the ETF calculator
      inputs stating plainly that this buys listed ETFs through a broker market order,
      not a mutual-fund SIP through the AMC/RTA, with a pointer to the Mutual fund tab.
      `research/sip.py::build_etf_sip`'s own `note` field (returned after building a mix)
      already said this in B4; this makes the distinction visible **before** the user
      builds a mix too, not only after.
- [x] **`lib/types.ts`**: `SuggestMixSleeve`, `SuggestMixResult`. **`lib/api.ts`**:
      `suggestFundMix`.
- [x] **Found and fixed a real bug while manually verifying B6 against the live
      backend** (not a frontend bug — a Python LLM-response-parsing bug, caught because
      this project's house rule is to actually run things, not just build and assume):
      `curl`-testing `POST /funds/sip/suggest` showed the `explanation` field contained a
      ~20KB Python list-repr dump including a huge opaque `signature` blob, instead of
      plain text. Root cause: this Gemini model returns `.content` as a list of
      structured content blocks (`[{"type": "text", "text": "...", "extras":
      {"signature": "<...>"}}]`) rather than a plain string, and **four separate call
      sites** across the codebase used the same fallback —
      `reply.content if isinstance(reply.content, str) else str(reply.content)` — which
      stringifies the entire block list (signature included) for any non-string shape.
      Affected: `research/sip.py` (both `_explain_fund_sip` and `_explain_suggestion`,
      added this session), `research/stock_score.py::_explain` (Step 3), and
      `research/guidance.py` (pre-existing, and worse there — that call site parses JSON
      out of the text, so a structured-block response wouldn't just look ugly, it would
      silently fail `json.loads` and fall through to the rule-based defaults every time).
      **Fix**: added `llm/factory.py::extract_text(content)` — a single shared helper
      that returns a string as-is, concatenates every block's `"text"` field for a list
      of structured blocks, and falls back to `str()` only for a genuinely unrecognized
      shape — and switched all four call sites to use it. Added 4 regression tests
      (`tests/unit/test_llm_factory.py`), including one asserting a `str`/`int` fallback
      and one with a multi-block list. Re-verified live: the same `curl` now returns a
      clean plain-English `explanation` sentence with no signature blob.
      **Process note**: the first live-backend check after this fix still showed the old
      broken output — not a fix failure, but three *stale* `uvicorn` processes from
      earlier sessions were still holding port 8000 (`pkill -f uvicorn` doesn't work
      against native Windows processes from this Git Bash tool; had to `taskkill //F
      //PID <pid> //T` each one by PID from `netstat -ano`). Worth remembering for any
      future live-backend check in this environment.
- [x] All green: `pnpm lint` clean, `pnpm build` clean (TypeScript + static generation);
      backend `ruff check src tests` clean, `mypy` on every touched file clean (one
      pre-existing, unrelated `guidance.py` union-attr error confirmed via `git stash` to
      predate this session — line number only shifted from the new import), full
      `pytest -q` → **128 passed**, same 1 known pre-existing failure
      (`test_settings_defaults`).

Files touched this step:
- `frontend/src/components/SuggestMixPanel.tsx` (new)
- `frontend/src/app/sip/page.tsx` (suggest tab wired to real panel, ETF persistent note)
- `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts` (suggest-mix types/API)
- `src/investment_agent/llm/factory.py` (`extract_text`, new)
- `src/investment_agent/research/sip.py`, `research/stock_score.py`,
  `research/guidance.py` (all switched to `extract_text`)
- `tests/unit/test_llm_factory.py` (+4 tests)

### B7 — DONE

- [x] **`docs/data-sources.md`**: new §4 "Mutual Fund Data Sources (Workstream B)" —
      documents AMFI (scheme master → `mutual_fund_schemes`, three deterministic
      classifiers) and mfapi.in (NAV history/search, confirmed live-reachable unlike
      NSE/BSE) as the two sources backing `/funds/*`; explicitly calls out the known,
      disclosed gap (no free TER/expense-ratio source — documented rather than silently
      worked around) and states the LTCG/STCG tax assumptions as module-level constants.
- [x] **`README.md`**: new "SIP Calculator: Real Mutual Funds and ETF Mixes" section
      under "Running the Application" with runnable `curl` examples for
      `GET /funds/search`, `GET /funds/{scheme_code}`, `POST /funds/sip/backtest`,
      `POST /funds/sip/project`, and `POST /funds/sip/suggest`, plus a note that
      `GET /funds/search`/`POST /funds/sip/suggest` degrade gracefully (not an error) if
      `POST /market/refresh` hasn't been run yet.

Files touched this step:
- `docs/data-sources.md` (new §4)
- `README.md` (new SIP calculator section)

### Currently in progress

**Workstream B (SIP calculator rebuild) is fully complete — B1 through B7 all DONE.**
Backend (`ruff`/`mypy`/`pytest`) and frontend (`pnpm lint`/`pnpm build`) are both green,
and the whole mutual-fund SIP path was manually verified end-to-end against the real
running backend (search fallback, fund detail, backtest, projection, suggest-a-mix, and
the `extract_text` bug fix) — see B6's notes above for the one real bug this surfaced and
fixed. Remember before the next real-world check: the real `mutual_fund_schemes` table is
still empty in the actual DB; `POST /market/refresh` needs to be triggered at some point
for `GET /funds/search` and `POST /funds/sip/suggest`'s fund-picking to have real
candidates instead of degrading to the mfapi.in fallback / `DATA_UNAVAILABLE` sleeves
(both are correct, intentional behavior until then, not bugs).

**Next action**: return to **Workstream A**, picking up at **Step 4** (F4 news
sentiment — upgrade Step 2's keyword-heuristic `filings_risk` to a real sentiment
pipeline, update the News tab), per the "Pending Tasks" ordering from earlier in this
file (Step 4 → Step 5 → Step 8; Steps 6/7 are superseded by what Workstream B just
built).

*(Superseded by the later note near the top of Workstream A's own section: both
workstreams were subsequently finished — Steps 4/5/7/8 all DONE. See
"Post-completion UX fixes" below for what came after that.)*

---

## Post-completion UX fixes (direct user feedback)

Both pasted specs were fully delivered (see above), but the user then actually tried
the UI and found three real usability gaps — exactly the kind of thing "both workstreams
done" doesn't guarantee on its own. Fixed all three.

### Fix 1 — Compare page had no way to discover a symbol

**User's words**: *"Side by side compare how am I suppose to know the code like TCS,
INFY"* — the `/compare` page's "Add symbol" was a bare text input; you had to already
know the exact ticker.
- [x] **`components/StockSearch.tsx`** (new) — debounced combobox over the existing
      `GET /market/search` (via `searchStocks`, already used by the `/stocks` list page,
      just never reused as a dropdown before), showing symbol + company name per result.
- [x] **`/compare` page** — replaced the plain input with `StockSearch`, and added a
      "Today's movers" quick-add row sourced from real `GET /market/trending` data (the
      same data the home page's "Biggest NSE moves" card already shows) — real, current
      symbols to click, not a hardcoded list.

### Fix 2 — SIP fund search had no way to discover a fund name

**User's words**: *"In SIP calculator there is no option for list only search input
field how I am suppose to know the names"* — same root problem, different page:
`FundSearch` only activated after typing 2+ characters, with nothing to prompt a
beginner who has no fund names to type.
- [x] **`components/FundSearch.tsx`** — added a "Not sure what to search? A few
      well-known funds to start from" quick-pick row, shown before any typing. Six real,
      verified scheme codes (checked live against mfapi.in during this fix, not
      guessed) spanning the common categories — large cap, flexi cap, an index fund, and
      small cap — not a claim that these are "the best" funds, just a starting point.

### Fix 3 — Chat assumed financial literacy a beginner doesn't have

**User's words** (quoting the actual transcript that triggered this): *"A beginner will
not have idea about all these, if a beginner asks the AI. Make it in such a way all
levels of stock marketers can ask and learn."* The transcript showed the chat asking
*"Which style fits you: large cap, flexi cap, mid cap, or small cap?"* to someone who had
just said *"I am very new to mutual fund."* This was two separate problems, not one:

1. **`research/chat.py` only ever knew about `build_etf_sip`** — a user asking "which
   mutual funds should I invest in" got an ETF-jargon answer because the chat had never
   been updated after Workstream B built `suggest_mix` (real mutual funds). Fixed: a
   monthly-investment request now routes to `suggest_mix` by default; only an explicit
   "ETF" mention still goes to `build_etf_sip`.
2. **Every question assumed the user already knew the answer's vocabulary and exact
   phrasing.** Fixed, in `research/chat.py`:
   - The risk question is now asked as a plain scenario ("how would you feel if your
     investment's value dropped for a while?") with lettered options (A/B/C), not a bare
     "cap style?" prompt — mapped to `conservative`/`moderate`/`aggressive` for
     `suggest_mix`, not the old ETF-only cap-style vocabulary.
   - Every question now accepts "I don't know"/"not sure" with a stated, sensible
     default (5 years; a balanced/moderate risk comfort) instead of looping forever on an
     answer a beginner may not have.
   - A bare terse reply ("5", "5000") is now understood **in context of whichever
     question was just asked** (tracked via a new `last_asked` field on the session
     state) — previously the regex-based parser required "5 years"/"₹5000" phrasing,
     which is exactly the kind of thing someone new to investing wouldn't think to add.
   - Fund categories (`"large cap"`, `"flexi cap"`, etc.) are translated to plain English
     everywhere a beginner would see them — not just in chat's own text, but at the
     source: `research/sip.py` gained `CATEGORY_PLAIN_LABELS` (the single shared
     translation table) and a new `category_label` field on every `suggest_mix` sleeve,
     and `_explain_suggestion`'s own LLM prompt was updated to use that plain wording
     instead of echoing the raw category names back — confirmed live (see verification
     below) that the LLM's own narration no longer says "large cap"/"flexi cap" either,
     not just the deterministic lines chat.py builds itself.
   - `app/chat/page.tsx`'s greeting, suggested prompts, and the "Style" fact-chip label
     (now "Risk comfort") were reworded to drop jargon too — a UI chip calling it "Style"
     is itself a tiny piece of unexplained jargon.
- [x] **Tests**: `tests/unit/test_chat.py` (new, 6 tests) — terse numeric answers
      understood in context, "I don't know" defaulting for both horizon and risk
      questions, the mutual-fund-routes-to-suggest_mix (not build_etf_sip) fix with an
      assertion that would fail loudly if that routing regressed, the explicit-ETF-still-
      works path, and stock intent correctly skipping the risk question (a stock pick
      has no "mix" to weight). All I/O (`suggest_mix`, `build_etf_sip`, `guide_symbol`)
      monkeypatched.
      All green: `ruff check src tests` clean, `mypy` clean on every touched file, full
      `pytest -q` → **168 passed**, same 1 known pre-existing failure
      (`test_settings_defaults`). `pnpm lint`/`pnpm build` clean.
      **Manually verified live** against the real running backend, replaying the user's
      own scenario verbatim (`"I want to invest Rs50000 these month"` → `"Monthly SIP"` →
      `"5"` → `"I dont know"`, and again with `"mutual funds, 50000 a month"` → `"5
      years"` → `"B"`): both runs produced a complete, jargon-free mutual-fund mix with a
      plain-English explanation, with no raw "large cap"/"flexi cap" anywhere in either
      the deterministic text or the LLM's own narration.
      **Known residual limitation, not fixed this round**: the real `mutual_fund_schemes`
      table is still unsynced in this environment, so the live-verified responses show
      "(no specific fund matched yet)" for each category rather than a real scheme name —
      correct, expected behavior (same caveat noted throughout Workstream B), not
      something this round of fixes could address without actually running
      `POST /market/refresh` against a real, populated database.

Files touched this round:
- `frontend/src/components/StockSearch.tsx` (new)
- `frontend/src/app/compare/page.tsx` (StockSearch + "Today's movers" quick-add)
- `frontend/src/components/FundSearch.tsx` (popular-funds quick-pick row)
- `frontend/src/app/chat/page.tsx` (greeting/suggestions/chip label reworded)
- `src/investment_agent/research/chat.py` (rewritten: plain-language questions,
  context-aware terse-answer parsing, "I don't know" defaults, routes to `suggest_mix`
  by default)
- `src/investment_agent/research/sip.py` (`CATEGORY_PLAIN_LABELS` extracted as the
  shared translation table, `category_label` added to every `suggest_mix` sleeve,
  `_explain_suggestion`'s LLM prompt updated to use plain wording)
- `tests/unit/test_chat.py` (new, 6 tests)

**Next action**: none scoped. Both workstreams remain complete; this was reactive UX
polish from direct user testing, not a new spec item. If the user finds more UI rough
edges, treat each the same way: reproduce in their own words, fix at the real source
(not just the one screen they noticed it on), and verify live.
