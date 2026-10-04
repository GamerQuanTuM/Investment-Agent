import {
  HealthStatus,
  BrokerVaultState,
  StockQuote,
  StockHistory,
  TrendingPage,
  IndexQuote,
  GuidanceNote,
  ResearchRunResult,
  FundamentalSnapshot,
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

export function sendChat(sessionId: string, message: string) {
  return fetch(`${API_BASE_URL}/research/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  }).then(async (res) => {
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{
      text: string;
      needs_input: boolean;
      collected: {
        intent: "stock" | "sip" | null;
        symbol: string | null;
        horizon_years: number | null;
        monthly_amount: number | null;
        risk: string | null;
      };
      guidance?: GuidanceNote;
      plan?: SipPlan;
    }>;
  });
}

export function fetchFundamentals(symbol: string): Promise<FundamentalSnapshot> {
  return readJson<FundamentalSnapshot>(`/research/${encodeURIComponent(symbol)}`);
}

export function runResearchPipeline(monthlyBudget: number, userId = "user_default"): Promise<ResearchRunResult> {
  return postJson<ResearchRunResult>("/research/run", {
    user_id: userId,
    monthly_budget: monthlyBudget,
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
