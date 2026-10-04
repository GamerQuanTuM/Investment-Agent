export interface HealthStatus {
  status: string;
  environment: string;
  timestamp: string;
  app_name?: string;
  dependencies?: Record<string, string>;
  routing_tiers?: Record<string, string>;
  primary_llm_provider?: string;
  primary_llm_model?: string;
}

export interface PortfolioHolding {
  symbol: string;
  company_name: string;
  quantity: number;
  avg_buy_price: number;
  current_ltp: number | null;
  current_value: number;
  invested_value: number;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  sector: string;
  allocation_pct: number;
}

export interface BrokerVaultState {
  broker_name: string;
  auth_status: "CONNECTED" | "DISCONNECTED";
  cash_available: number | null;
  portfolio_total_value: number | null;
  day_change_pnl: number | null;
  day_change_pct: number | null;
  holdings: PortfolioHolding[];
}

export interface StockQuote {
  symbol: string;
  name: string;
  live_price: number;
  day_change: number;
  day_change_percentage: number;
  day_open?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  prev_close?: number | null;
  volume: number;
  pe_ratio?: number | null;
  market_cap_cr?: number | null;
  as_of?: string;
}

export interface TrendingPage {
  items: StockQuote[];
  offset: number;
  limit: number;
  next_offset: number | null;
  total: number;
  as_of: string;
  pending?: boolean;
  scanned?: number;
  universe?: number;
}

export interface Candle {
  ts: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

export interface StockHistory {
  symbol: string;
  range: string;
  interval: string;
  candles: Candle[];
}

export interface IndexQuote {
  symbol?: string;
  name: string;
  bucket?: string;
  live_price: number;
  day_change_percentage: number;
}

export interface GuidanceNote {
  symbol: string;
  name?: string;
  stance: "CONSIDER" | "WAIT" | "AVOID";
  summary: string;
  reasons: string[];
  blockers: string[];
  /** Plain-English, beginner-friendly strengths — no jargon. */
  good_points?: string[];
  /** Plain-English, beginner-friendly risks/weaknesses — no jargon. */
  bad_points?: string[];
  /** 3-5 sentence plain-English verdict for someone who has never bought a stock. */
  verdict_explanation?: string;
  risk_level?: "LOW" | "MEDIUM" | "HIGH";
  horizon_years: number;
  monthly_budget?: number;
  /** How many whole shares the monthly budget buys at the live price. */
  shares_to_buy?: number | null;
  /** Monthly budget left over after buying `shares_to_buy` whole shares. */
  leftover_cash?: number | null;
  live_price?: number;
  pe_ratio?: number | null;
  one_year_price_change_pct?: number | null;
  fundamentals?: Record<string, number | string | null>;
  source?: string;
}

export interface ResearchCandidate {
  symbol: string;
  company_name: string;
  sector: string;
  market_cap_cr: number;
  pe_ratio: number;
  debt_to_equity: number;
  promoter_pledge_pct: number;
  roce_pct: number;
  free_cash_flow_3y_cagr_pct: number;
  revenue_3y_cagr_pct: number;
}

/** FACT/INTERPRETATION/ASSUMPTION/UNCERTAINTY/RISK partition built by investment_report_node. */
export interface ResearchReport {
  title: string;
  date: string;
  decision: string;
  FACT: string[];
  INTERPRETATION: string[];
  ASSUMPTION: string[];
  UNCERTAINTY: string[];
  RISK: string[];
  EVIDENCE_SOURCES: { source_name?: string; source_url?: string }[];
}

export interface BullCase {
  thesis: string[];
  supporting_evidence: (string | null)[];
  assumptions: string[];
}

export interface BearCase {
  counterarguments: string[];
  negative_evidence: string[];
  thesis_break_conditions: string[];
}

/** The real shape recommendation_gate_node / investment_report_node produce — not a
 *  fixed ACCUMULATE/HOLD/TRIM/REJECT rubric, just OPPORTUNITY or NO_ACTION. */
export interface ResearchRecommendation {
  decision: "OPPORTUNITY" | "NO_ACTION";
  asset_id?: string;
  name?: string;
  reason?: string;
  status?: string;
  proposed_monthly_allocation?: number;
  horizon_years?: number;
  action_items?: string[];
  report?: ResearchReport;
}

export interface FundamentalSnapshot {
  asset_id: string;
  status: "SNAPSHOT" | "DATA_UNAVAILABLE";
  market: string;
  message?: string;
  source_name?: string;
  source_url?: string;
  data_date?: string;
  roe_pct?: number | null;
  eps?: number | null;
}

export interface ResearchRunResult {
  status: string;
  decision: "OPPORTUNITY" | "NO_ACTION";
  confidence: number;
  evidence_quality: string;
  recommendation: ResearchRecommendation;
  bull_case?: BullCase | null;
  bear_case?: BearCase | null;
  warnings: string[];
  errors: string[];
}
