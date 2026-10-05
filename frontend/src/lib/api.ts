import {
  ChatReply,
  HealthStatus,
  BrokerVaultState,
  StockQuote,
  StockHistory,
  TrendingPage,
  IndexQuote,
  GuidanceNote,
  ResearchRunResult,
  FundamentalSnapshot,
  StockFilings,
  StockShareholding,
  StockScore,
  StockNews,
  MacroSnapshot,
  ConcentrationReport,
  PortfolioAlert,
  CompareResult,
  FundSearchResult,
  FundDetail,
  FundSipBacktestResult,
  FundSipProjectResult,
  SuggestMixResult,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function readJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text();
    let message = detail || `Request failed (${res.status})`;
    try {
      const body = JSON.parse(detail) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) message = body.detail;
    } catch {
      message = detail || message;
    }
    throw new Error(message);
  }
  return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    let message = detail || `Request failed (${res.status})`;
    try {
      const parsed = JSON.parse(detail) as { detail?: unknown };
      if (typeof parsed.detail === "string" && parsed.detail) message = parsed.detail;
    } catch {
      message = detail || message;
    }
    throw new Error(message);
  }
  return res.json();
}

export function fetchHealthStatus(): Promise<HealthStatus> {
  return readJson<HealthStatus>("/health");
}

export function fetchBrokerVault(): Promise<BrokerVaultState> {
  return readJson<BrokerVaultState>("/market/portfolio");
}

export function fetchIndices(): Promise<{ items: IndexQuote[] }> {
  return readJson<{ items: IndexQuote[] }>("/market/indices");
}

export function fetchMacroSnapshot(): Promise<MacroSnapshot> {
  return readJson<MacroSnapshot>("/market/macro");
}

export function fetchMarketStatus(): Promise<{
  indstocks_configured: boolean;
  watchlist: string[];
  amfi_scheme_codes: string[];
  fundamentals: string;
}> {
  return readJson("/market/status");
}

export function refreshMarket(): Promise<Record<string, unknown>> {
  return postJson("/market/refresh", {});
}

export function fetchTrending(offset: number, exchange = "NSE"): Promise<TrendingPage> {
  return readJson<TrendingPage>(
    `/market/trending?offset=${offset}&limit=20&exchange=${exchange}`,
  );
}

export function searchStocks(query: string, exchange = "NSE") {
  return readJson<{ items: { symbol: string; name: string; exchange: string }[] }>(
    `/market/search?q=${encodeURIComponent(query)}&exchange=${exchange}`,
  );
}

export function fetchQuote(symbol: string, exchange = "NSE"): Promise<StockQuote> {
  return readJson<StockQuote>(
    `/market/stocks/${encodeURIComponent(symbol)}?exchange=${exchange}`,
  );
}

export function fetchHistory(symbol: string, range: string, exchange = "NSE"): Promise<StockHistory> {
  return readJson<StockHistory>(
    `/market/stocks/${encodeURIComponent(symbol)}/history?range=${range}&exchange=${exchange}`,
  );
}

export function fetchGuidance(
  symbol: string,
  horizonYears: number,
  monthlyBudget: number,
  exchange = "NSE",
  horizonMonths = 0,
): Promise<GuidanceNote> {
  return fetch(`${API_BASE_URL}/research/guidance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbol,
      exchange,
      horizon_years: horizonYears,
      horizon_months: horizonMonths,
      monthly_budget: monthlyBudget,
    }),
  }).then(async (res) => {
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || "Guidance failed");
    }
    return res.json();
  });
}

export interface SipPlan {
  style: string;
  requested_style: string;
  horizon_years: number;
  monthly_amount: number;
  note: string;
  sleeves: {
    symbol: string;
    label: string;
    weight_pct: number;
    monthly_inr: number;
    live_price: number | null;
    units: number | null;
  }[];
}

const CHAT_TIMEOUT_MS = 90_000;

export async function sendChat(sessionId: string, message: string) {
  // Never leave the chat spinning forever: give up after 90 s with a message the user can act on.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}/research/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as ChatReply;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("That took too long. Please try again in a moment.");
    }
    if (err instanceof TypeError) {
      throw new Error("I couldn't reach the server. Check that the backend is running, then try again.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function fetchFundCatalogue(offset: number, query = "", category = "") {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: "40",
  });
  if (query) params.set("q", query);
  if (category) params.set("category", category);
  return readJson<{
    source: string;
    scheme_count: number;
    fund_house_count: number;
    fund_houses: { name: string; scheme_count: number }[];
    categories: { name: string; count: number }[];
    items: { scheme_code: string; scheme_name: string; fund_house: string; category: string | null }[];
    total: number;
    next_offset: number | null;
  }>(`/funds/catalogue?${params.toString()}`);
}

export function fetchFundamentals(symbol: string): Promise<FundamentalSnapshot> {
  return readJson<FundamentalSnapshot>(`/research/${encodeURIComponent(symbol)}`);
}

export function fetchFilings(symbol: string): Promise<StockFilings> {
  return readJson<StockFilings>(`/market/stocks/${encodeURIComponent(symbol)}/filings`);
}

export function fetchShareholding(symbol: string): Promise<StockShareholding> {
  return readJson<StockShareholding>(`/market/stocks/${encodeURIComponent(symbol)}/shareholding`);
}

export function fetchStockScore(symbol: string, exchange = "NSE"): Promise<StockScore> {
  return readJson<StockScore>(`/research/score/${encodeURIComponent(symbol)}?exchange=${exchange}`);
}

export function fetchStockNews(symbol: string, name?: string): Promise<StockNews> {
  const params = name ? `?name=${encodeURIComponent(name)}` : "";
  return readJson<StockNews>(`/market/stocks/${encodeURIComponent(symbol)}/news${params}`);
}

export function fetchPortfolioConcentration(): Promise<ConcentrationReport> {
  return readJson<ConcentrationReport>("/market/portfolio/concentration");
}

export function fetchPortfolioAlerts(): Promise<{ alerts: PortfolioAlert[] }> {
  return readJson<{ alerts: PortfolioAlert[] }>("/market/portfolio/alerts");
}

export function compareStocks(symbols: string[], exchange = "NSE"): Promise<CompareResult> {
  return readJson<CompareResult>(
    `/research/compare?symbols=${encodeURIComponent(symbols.join(","))}&exchange=${exchange}`,
  );
}

export function runResearchPipeline(monthlyBudget: number, userId = "user_default"): Promise<ResearchRunResult> {
  return postJson<ResearchRunResult>("/research/run", {
    user_id: userId,
    monthly_budget: monthlyBudget,
  });
}

export function searchFunds(query: string, category?: string, plan?: string): Promise<FundSearchResult> {
  const params = new URLSearchParams({ q: query });
  if (category) params.set("category", category);
  if (plan) params.set("plan", plan);
  return readJson<FundSearchResult>(`/funds/search?${params.toString()}`);
}

export function fetchFundDetail(schemeCode: string): Promise<FundDetail> {
  return readJson<FundDetail>(`/funds/${encodeURIComponent(schemeCode)}`);
}

export function fundSipBacktest(
  schemeCode: string,
  monthly: number,
  stepUpPct = 0,
  startDate?: string,
): Promise<FundSipBacktestResult> {
  return postJson<FundSipBacktestResult>("/funds/sip/backtest", {
    scheme_code: schemeCode,
    monthly,
    step_up_pct: stepUpPct,
    start_date: startDate ?? null,
  });
}

export function fundSipProject(
  monthly: number,
  years: number,
  annualReturnPct: number,
  stepUpPct = 0,
  inflationPct = 0,
): Promise<FundSipProjectResult> {
  return postJson<FundSipProjectResult>("/funds/sip/project", {
    monthly,
    years,
    annual_return_pct: annualReturnPct,
    step_up_pct: stepUpPct,
    inflation_pct: inflationPct,
  });
}

export function suggestFundMix(
  monthly: number,
  horizonYears: number,
  riskProfile: string,
  spanYears: number,
  spanMonths: number,
): Promise<SuggestMixResult> {
  return postJson<SuggestMixResult>("/funds/sip/suggest", {
    monthly,
    horizon_years: horizonYears,
    risk_profile: riskProfile,
    return_span: "custom",
    span_years: spanYears,
    span_months: spanMonths,
  });
}

export function planSip(monthlyAmount: number, horizonYears: number, style: string) {
  return fetch(`${API_BASE_URL}/research/sip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      monthly_amount: monthlyAmount,
      horizon_years: horizonYears,
      style,
    }),
  }).then(async (res) => {
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<SipPlan>;
  });
}
