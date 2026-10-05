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

export interface Filing {
  symbol: string | null;
  subject: string;
  category: string;
  announced_at: string | null;
  attachment_url: string | null;
  source_name: string;
  source_url: string;
}

export interface StockFilings {
  symbol: string;
  status: "OK" | "DATA_UNAVAILABLE";
  filings: Filing[];
}

export interface ShareholdingQuarter {
  period_end: string | null;
  promoter_pct: number | null;
  promoter_pledge_pct: number | null;
  fii_pct: number | null;
  dii_pct: number | null;
  public_pct: number | null;
}

export interface StockShareholding {
  symbol: string;
  status: "OK" | "DATA_UNAVAILABLE";
  quarters: ShareholdingQuarter[];
}

export interface ConcentrationReport {
  sector_exposure_pct: Record<string, number>;
  biggest_sector: string | null;
  biggest_sector_pct: number | null;
  biggest_holding_symbol: string | null;
  biggest_holding_pct: number | null;
  diversification_score: number | null;
  concentration_flags: string[];
}

export interface PortfolioAlert {
  symbol: string | null;
  severity: "INFO" | "WARNING";
  kind: "DRAWDOWN" | "CONCENTRATION" | "SECTOR_CONCENTRATION";
  message: string;
}

export interface CompareResult {
  symbols: string[];
  items: StockScore[];
}

export interface MacroFieldUsdInr {
  status: "OK" | "DATA_UNAVAILABLE";
  value?: number;
  data_date?: string;
  source_name?: string;
  source_url?: string;
}

export interface MacroFieldCpi {
  status: "OK" | "DATA_UNAVAILABLE";
  value_pct?: number;
  data_date?: string;
  source_name?: string;
  source_url?: string;
}

export interface MacroSnapshot {
  usd_inr: MacroFieldUsdInr;
  cpi_inflation_yoy: MacroFieldCpi;
}

export interface NewsArticle {
  title: string;
  link: string | null;
  source_name: string;
  published_at: string | null;
}

export interface NewsSentiment {
  label: "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "DATA_UNAVAILABLE";
  score: number | null;
  positive_count: number;
  negative_count: number;
  total_articles: number;
}

export interface StockNews {
  symbol: string;
  status: "OK" | "DATA_UNAVAILABLE";
  articles: NewsArticle[];
  sentiment: NewsSentiment;
}

export interface ScoreInput {
  label: string;
  value: number | null;
  unit: string;
  benchmark: number | null;
  benchmark_label: string | null;
}

export interface ScoreBlock {
  score: number | null;
  inputs: ScoreInput[];
}

export interface StockScore {
  symbol: string;
  name?: string;
  status: "OK" | "DATA_UNAVAILABLE";
  message?: string;
  quality?: ScoreBlock;
  valuation?: ScoreBlock;
  momentum?: ScoreBlock;
  risk?: ScoreBlock;
  overall?: number | null;
  explanation?: string;
  valuation_note?: string;
  data_as_of?: string | null;
}

export interface FundSummary {
  scheme_code: string;
  name: string;
  fund_house: string | null;
  category: string | null;
  sebi_group: string | null;
  plan: string | null;
  option: string | null;
  latest_nav: number | null;
  nav_date: string | null;
}

export interface FundSearchResult {
  query: string;
  source: "database" | "mfapi.in";
  items: (FundSummary | { scheme_code: string; scheme_name: string })[];
}

export interface FundDetail {
  scheme_code: string;
  status: "OK" | "DATA_UNAVAILABLE";
  message?: string;
  facts: FundSummary | null;
  trailing_returns_pct?: { "1y": number | null; "3y": number | null; "5y": number | null; "10y": number | null };
  risk?: { max_drawdown_pct: number; annualized_volatility_pct: number | null };
  rolling_3y_return_pct?: { best_pct: number | null; worst_pct: number | null };
  data_as_of?: string | null;
  source_name?: string;
  source_url?: string;
}

export interface FundSipBacktestResult {
  scheme_code: string;
  scheme_name: string | null;
  invested: number | null;
  units: number | null;
  current_value: number | null;
  xirr_pct: number | null;
  start_date: string | null;
  end_date: string | null;
}

export interface FundSipProjectResult {
  assumption_note: string;
  invested: number;
  nominal_corpus: number;
  inflation_adjusted_corpus: number;
}

export interface SuggestMixFund {
  scheme_code: string;
  scheme_name: string;
  trailing_return_pct_used: number;
  return_window: string;
}

export interface SuggestMixSleeve {
  category: string;
  category_label?: string;
  weight_pct: number;
  monthly_inr: number;
  status: "OK" | "DATA_UNAVAILABLE";
  scheme_code: string | null;
  scheme_name: string | null;
  trailing_return_pct_used?: number | null;
  return_window?: string | null;
  has_full_5y_history?: boolean;
  projected_corpus?: number | null;
  funds?: SuggestMixFund[];
}

export interface SuggestMixResult {
  mode: "suggest";
  risk_profile: string;
  horizon_years: number;
  monthly_amount: number;
  return_span?: string;
  return_span_label?: string;
  sleeves: SuggestMixSleeve[];
  note: string;
  explanation: string;
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

/** One source behind a figure, as returned in the `sources` array of a chat reply. */
export interface EvidenceItem {
  claim: string;
  source_name: string;
  source_url: string;
  source_type: string;
  data_date: string | null;
  retrieved_at: string;
}

export interface StockPlanRow {
  symbol: string;
  name: string;
  sector: string;
  market_cap_band: string;
  price: number | null;
  shares: number;
  amount_inr: number;
  weight_pct: number;
  target_weight_pct: number;
  score: number;
  /** Top two measured factors, e.g. "Business quality 78/100 (ROE 22.1%)". */
  why: string[];
  data_as_of: string;
}

export interface StockPlan {
  status: "OK";
  budget: number;
  rows: StockPlanRow[];
  total_invested: number;
  leftover: number;
  data_as_of: string | null;
  sector_split: { sector: string; pct: number }[];
  caveats: string[];
  reality_check: string | null;
  growth_note: string;
  disclaimer: string;
  risk_profile: string;
}

export interface GlossaryEntry {
  term: string;
  definition: string;
  example: string;
}

export interface ChatComparison {
  title: string;
  columns: string[];
  rows: { label: string; a: string; b: string; c?: string }[];
  takeaway: string;
}

export interface ChatCollected {
  intent: string | null;
  symbol: string | null;
  horizon_years: number | null;
  monthly_amount: number | null;
  amount_inr: number | null;
  amount_kind: "lump_sum" | "monthly" | null;
  risk: string | null;
  stock_count: number | null;
  experience_level: "beginner" | "intermediate" | null;
}

export interface ChatReply {
  session_id: string;
  text: string;
  needs_input: boolean;
  error?: boolean;
  intent: string | null;
  collected: ChatCollected;
  suggestions: string[];
  sources: EvidenceItem[];
  data_status?: "DATA_UNAVAILABLE" | "LOADING";
  assumed?: { horizon_years: number; risk_profile: string };
  stock_plan?: StockPlan | null;
  glossary?: GlossaryEntry;
  comparison?: ChatComparison;
  notice?: string;
  guidance?: GuidanceNote;
  plan?: {
    kind?: "monthly" | "lump_sum";
    title?: string;
    style: string;
    horizon_years: number;
    monthly_amount?: number;
    amount_inr?: number;
    note: string;
    sleeves: {
      symbol: string;
      label: string;
      weight_pct: number;
      monthly_inr?: number;
      amount_inr?: number;
      scheme_name?: string | null;
      units?: number | null;
      return_3y_pct?: number | null;
      return_5y_pct?: number | null;
    }[];
    spread_option?: { months: number; monthly_inr: number; note: string };
  };
}
