# Chat: intents, slots and the stock-list planner

`POST /research/chat` is one conversational turn. Everything numeric is computed in Python;
a model may only classify the message, phrase a result the code already produced, or (for
concepts outside the glossary) explain an idea under a restricted prompt.

```
message ─► chat_intent.extract ─► intent + slots ─► handler ─► reply (+ suggestions, sources)
                │                                       │
        cheap LLM → JSON → pydantic                     └─ state saved: Redis `chat:{session_id}` (24h)
        rules fallback (always run)                        with in-memory fallback, last 6 turns kept
```

## Intents

| Intent | Meaning | Handler |
|---|---|---|
| `education` | "what is an ETF / SIP / P/E / NAV / ELSS / demat", "how does the market work" | `research/education.py` |
| `compare` | "difference between ETF and mutual fund", "SIP vs lump sum", "ETF or index fund" | `research/education.compare` → `research/glossary.py` |
| `stock_list` | "give me N stocks for ₹X" | `research/stock_list_chat.py` → `portfolio/stock_picker.py` |
| `stock_single` | a named stock ("should I buy TCS") | `research/guidance.py` (asks horizon + amount if missing) |
| `plan_sip_fund` | mutual-fund plan, monthly or one-time | `research/sip.suggest_mix` / `suggest_lump_sum` |
| `plan_sip_etf` | monthly ETF plan | `research/sip.build_etf_sip` |
| `fund_list` | "name some mutual funds" | `research/sip.rank_funds` |
| `market_overview` | "how is the market today" | `research/chat_market.py` |
| `portfolio_help` | "how concentrated is my portfolio" | `research/chat_market.py` |
| `answer` | reply to the pending question, or a tweak of the last plan | continues the open/last flow |
| `off_topic` | not about investing | polite redirect + 3 example chips |
| `unclear` | investing-related but ambiguous | one question with 3-4 quick-reply chips |

**Slots:** `amount_inr`, `amount_kind` (`lump_sum`/`monthly`), `horizon_years`,
`risk_profile`, `stock_count` (+ `stock_count_min` for ranges such as "10-12"), `symbol`,
`concept`, `term_a` / `term_b` (the two things in a comparison), `experience_level` (`beginner`/`intermediate`), `sectors_wanted`.
A message that carries several slots fills them all at once and nothing already given is
re-asked. Defaults: horizon 5 years, risk moderate (large-cap-heavy for a beginner who did
not choose), 10 stocks, clamped to 3-15.

### How the intent is decided

1. `chat_intent.extract_slots` and `rule_intent` always run (deterministic, regex + glossary).
2. A short reply to a question we just asked (`last_asked`) is an `answer` without calling a model.
3. Otherwise the cheap-tier model returns JSON, validated by pydantic. Invalid, unparseable
   or failed output is discarded and the rules decide. Model-supplied numbers are kept only if
   the digits appear in the user's text, and the rules override two known failure modes
   (a multi-stock request labelled `stock_single`; a financial message labelled `unclear`).
4. **Symbols never come from the model or from "any capitalised word".** `resolve_symbols`
   matches only the real security master (`market/universe.load_symbol_master`: instrument
   master plus fundamental snapshots) by exact symbol or company-name search. "OK", "YES",
   "NO" and finance jargon are never tickers. If nothing matches, the user is asked to pick
   from real search results.

## Sessions

`research/chat_session.py` stores `{intent, slots, last_asked, last_result, history}` under
`chat:{session_id}` in Redis (24 h TTL, via `market/cache.py`) and keeps an in-process copy as
the fallback when Redis is down. `last_result` lets follow-ups ("make it 8 stocks", "what
about safer ones?") modify the previous plan instead of restarting. Saying "start over"
clears the session.

## Stock list (`stock_list`)

`portfolio/stock_picker.py`, Python only:

1. **Universe**: `FundamentalSnapshot` ⨝ latest `DailyBar` closes, scored with
   `portfolio/scoring.py` (quality, valuation, momentum, risk, overall).
2. **Exclusions**: missing price, price older than `MARKET_DATA_MAX_AGE_HOURS`, missing
   fundamentals (no quality score), market cap below `STOCK_PICK_MIN_MARKET_CAP_CR`, average
   volume below `STOCK_PICK_MIN_AVG_VOLUME`.
3. **Selection**: rank by overall score; at most 2 per sector; market-cap mix by risk profile
   (conservative: ≤20% mid, no small; moderate: ≤40% mid, ≤10% small; aggressive: ≤50% / ≤30%).
4. **Allocation**: weights proportional to score, each between half of an equal split and
   `max(20%, 2/N)`, no sector above 30% of the budget; then `shares = floor(allocation / price)`.
   A stock priced above its allocation is dropped and the next candidate takes its place.
5. **Output** (`stock_plan`): per stock symbol, name, sector, price, shares, amount, weight,
   score and the top two measured factors; plus `total_invested`, `leftover`, `data_as_of`,
   `sector_split`, `caveats`, `reality_check`, `disclaimer`.

*Reality check*: when the average position is under ₹5,000 the reply always explains that whole
shares leave cash unused and that brokerage/DP charges weigh more on small positions, and
offers "Prefer one index fund/ETF SIP instead?", which routes to `suggest_mix` with the same
amount.

*Future potential* is never predicted: only past 3-year revenue/profit CAGR, ROE/ROCE and
P/E versus sector peers are shown, labelled "past growth and quality, not a forecast". There
are no target prices or expected returns anywhere.

*Narration guard* (`research/llm_guard.py`): the cheap model may write a 2-3 sentence intro
from the structured JSON. Every ticker and number in it must appear in the structured result,
and forecast language is rejected; otherwise the deterministic template is used. The per-stock
lines, totals, caveats and the disclaimer are always template text.

### Where the stock universe comes from

1. **Database** (normal case): stored fundamentals + daily bars, filled by the background sync.
2. **Live fallback**: when the database has no eligible stocks (first run, failed sync),
   `market/live_universe.py` builds the candidate universe live from a reviewed Nifty 50 / Nifty
   Next 50 list (`market/index_constituents.py`, with a "last reviewed" date). Each name needs a
   live Yahoo quote, one-year price history and company ratios (TradingView fills gaps; ROCE and
   growth are computed in Python). Calls are bounded (8 at a time, per-call timeout, 3 attempts,
   1-hour Redis cache). Names with no provider data are dropped, never guessed. The result is
   scored by the same code as stored data and written back to the database, so the next request
   is instant. Only one fetch runs at a time; every request shares it.
3. While it runs the reply says "I'm loading fresh market data, this takes about a minute" and
   offers a **Try again** chip (`data_status: "LOADING"`); tapping it re-runs the same request.
   Only if both the database and the live fetch fail does it say "I couldn't reach the market data
   providers right now, please try again in a few minutes" (`data_status: "DATA_UNAVAILABLE"`).
   Replies never mention API endpoints.

### Background sync (`market/auto_sync.py`)

Started from the app lifespan without blocking startup; it never raises (failures are logged and
the loop continues). It syncs at once when the database is empty or older than
`MARKET_DATA_MAX_AGE_HOURS`, then re-checks every 15 minutes: while the NSE is open (Mon-Fri
09:15-15:30 IST) it syncs every `MARKET_SYNC_INTERVAL_HOURS`; outside market hours it syncs once
after each close. A sync runs `refresh_market_data()` (watchlist fundamentals, AMFI scheme master,
INDstocks bars when configured) and the live universe refresh. `GET /market/status` reports
`last_sync_at`, `rows` per table, `sync_in_progress` and `last_sync_error`.

## One-time vs monthly amounts, and fund plans

The amount's kind is never assumed (`chat_intent._amount_kind`). "per month", "every month",
"monthly" and "SIP of X" mean monthly; "lump sum", "one-time", "capital", "savings", "corpus",
"bonus", "I have X" and "invest X now" mean one-time; a bare "SIP" means monthly. If a fund or
ETF plan has an amount but no kind (for example "invest 20000"), the chat asks one question with
the chips **One-time amount** / **Every month** before building anything. A bare number typed in
answer to "how much every month?" is monthly.

- **Monthly** goes to `suggest_mix` (unchanged). Each category line shows the top fund's name,
  rupees a month, weight and its return over the ranking window, plus a source chip per fund.
- **One-time** goes to `suggest_lump_sum` (`research/sip.py`): the same category weights and
  fund ranking, but per fund it returns rupees of the lump sum, weight, units at the latest NAV
  and 3-year / 5-year annual returns when the history covers them. It also returns
  `spread_option`: invest over 6, 9 or 12 months (12 at 70%+ equity, 9 at 40%+, else 6) with the
  monthly amount computed in Python, presented as an option, not advice. Titles say
  "₹50,000 one-time", never "/month"; a category with no scorable fund says "no fund matched,
  data unavailable" instead of naming one.
- **Beginners** are not asked horizon and risk for a fund/ETF plan: the reply states the defaults
  it assumed (5 years, balanced) and offers "What about 10 years?" / "What about a safer mix?" /
  "What about higher risk?" chips to change them.
- **Money text** everywhere uses `research/formatting.py`: `inr()` gives ₹20,000 / ₹1,00,000 (Indian
  grouping, no ".0", no "INR"), `pct()` gives 12.5% / 40%, and `normalize_money_text()` rewrites
  amounts inside model-written paragraphs the same way.

## Education

Fixed, reviewed definitions in `research/glossary.py` (ETF, SIP, mutual fund, NAV, expense
ratio, P/E, ROE, market cap, large/mid/small cap, index fund, ELSS, demat, LTCG/STCG,
diversification, dividend, IPO, risk vs return, how the market works, share). A glossary hit
needs no market data and never asks for amount or horizon; it returns `glossary:
{term, definition, example}` and one next-step chip. Concepts outside the glossary go to the
cheap model under a system prompt that forbids prices, returns, tickers and recommendations;
a mechanical check discards any reply containing digits, currency, tickers or advice, and the
user then gets the list of terms we can explain.

### Comparisons (`compare`)

`chat_intent` recognises "difference between X and Y", "X vs Y", "compare X and Y", "how is X
different from Y" and "X or Y, which is better" (the bare "X or Y" form only when both sides are
terms we know, and never when the message is a request such as "suggest stocks or funds for
10000"). It fills `term_a` / `term_b` and the rules win over a model that collapses the question
into a single definition. `glossary.find_terms()` returns every glossary term in a message in
order (`find_term()` still returns just one).

`education.compare` answers in three tiers:

1. **Curated table** (`glossary.py`): ETF vs mutual fund, SIP vs lump sum, index vs active fund,
   direct vs regular plan, growth vs IDCW/dividend option, large vs mid vs small cap (and each
   pair), stocks vs mutual funds, ELSS vs normal equity fund, FD vs mutual fund, equity vs debt
   fund, ETF vs index fund. Rows: How you buy, Needs a demat account, Minimum amount, Costs, Who
   it suits, Main risk, plus a one-line "which is simpler for a beginner". Reviewed text only, no
   figures that change. Columns follow the order the user asked in.
2. **Composed from definitions**: both terms are in the glossary but there is no curated table
   (for example NAV vs P/E): the two definitions and examples side by side.
3. **Guarded model** for a term outside the glossary: same restricted prompt and mechanical check
   as `education` (no digits, currency, tickers or advice), else an honest "I don't have a
   reviewed comparison for those two yet".

The reply adds `comparison: {title, columns, rows: [{label, a, b, c?}], takeaway}` (`c` only for
the three-way cap table). The chat UI renders it as `ComparisonCard`: a table from tablet width,
stacked rows on a phone. Chips: "Plan a SIP in a mutual fund", "What is NAV?" (stock pairs offer
"Suggest 10 stocks for ₹10,000").

## Response contract

```jsonc
{
  "session_id": "…", "text": "…", "needs_input": false, "intent": "stock_list",
  "collected": { "intent", "symbol", "horizon_years", "monthly_amount", "amount_inr",
                 "amount_kind", "risk", "stock_count", "experience_level" },
  "suggestions": ["quick-reply chip", "…"],
  "sources": [ /* Evidence: claim, source_name, source_url, source_type, data_date */ ],
  "stock_plan": { "rows": [], "total_invested": 0, "leftover": 0, "data_as_of": "YYYY-MM-DD",
                  "caveats": [], "reality_check": "…", "sector_split": [], "disclaimer": "…" },
  "comparison": { "title", "columns": ["A","B"], "rows": [{ "label", "a", "b" }], "takeaway" },
  "plan": { "kind": "monthly" | "lump_sum", "title": "₹50,000 one-time", "sleeves": [], "spread_option": {} },
  "assumed": { "horizon_years": 5, "risk_profile": "moderate" },   // only when defaults were assumed
  "guidance": {}, "ranking": [], "glossary": { "term", "definition", "example" },
  "data_status": "LOADING" | "DATA_UNAVAILABLE"   // only when data is loading / missing
}
```

Fields other than `session_id`, `text` and `needs_input` are additive; older clients that
read only those keep working.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `MARKET_DATA_MAX_AGE_HOURS` | 36 | A stock whose latest price is older is excluded |
| `STOCK_PICK_MIN_MARKET_CAP_CR` | 5000 | Market-cap floor (₹ crore) |
| `STOCK_PICK_MIN_AVG_VOLUME` | 100000 | 20-day average volume floor (shares), applied when volume is stored |
| `MARKET_AUTO_SYNC_ENABLED` | true | Run the background sync from the app lifespan (off when `APP_ENV=test`) |
| `MARKET_SYNC_INTERVAL_HOURS` | 6 | Re-sync interval while the market is open |
| `LIVE_UNIVERSE_CONCURRENCY` | 8 | Parallel provider calls in the live fallback |
| `LIVE_UNIVERSE_CALL_TIMEOUT_SECONDS` | 15 | Timeout per provider call |
| `LIVE_UNIVERSE_WAIT_SECONDS` | 20 | How long a chat request waits for the live fetch before saying "loading" |
