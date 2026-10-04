"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Sparkles,
  BarChart3,
  FileSpreadsheet,
  LogIn,
  LogOut,
  ArrowUpToLine,
  ArrowDownToLine,
  BarChart2,
  Percent,
  Building2,
  Star,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  Megaphone,
  PieChart,
  Gauge,
  Newspaper,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import {
  fetchFilings,
  fetchFundamentals,
  fetchHistory,
  fetchQuote,
  fetchShareholding,
  fetchStockNews,
  fetchStockScore,
} from "@/lib/api";
import { MarketLoadingScreen } from "@/components/MarketLoadingScreen";
import { PriceChart } from "@/components/PriceChart";
import { AgentGuidance } from "@/components/AgentGuidance";
import { ScoreRing } from "@/components/ScoreRing";
import type { ScoreBlock } from "@/lib/types";

const RANGES = ["1d", "1w", "1m", "3m", "6m", "1y", "5y"] as const;
const TABS = [
  { id: "overview", label: "Chart", icon: BarChart3 },
  { id: "score", label: "Score", icon: Gauge },
  { id: "fundamentals", label: "Fundamentals", icon: FileSpreadsheet },
  { id: "filings", label: "Filings", icon: Megaphone },
  { id: "news", label: "News", icon: Newspaper },
  { id: "shareholding", label: "Shareholding", icon: PieChart },
  { id: "guidance", label: "AI guidance", icon: Sparkles },
] as const;

const SCORE_BLOCKS: { key: "quality" | "valuation" | "momentum" | "risk"; label: string }[] = [
  { key: "quality", label: "Quality" },
  { key: "valuation", label: "Valuation" },
  { key: "momentum", label: "Momentum" },
  { key: "risk", label: "Risk" },
];

const SHAREHOLDING_SEGMENTS = [
  { key: "promoter_pct", label: "Promoter", color: "var(--section-portfolio)" },
  { key: "fii_pct", label: "FII", color: "var(--section-research)" },
  { key: "dii_pct", label: "DII", color: "var(--section-sip)" },
  { key: "public_pct", label: "Public", color: "var(--text-muted)" },
] as const;

export default function StockPage() {
  const params = useParams<{ symbol: string }>();
  const search = useSearchParams();
  const exchange = search.get("exchange") === "BSE" ? "BSE" : "NSE";
  const symbol = decodeURIComponent(params.symbol || "").toUpperCase();
  const [range, setRange] = useState<(typeof RANGES)[number]>("1y");
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("overview");
  const [watched, setWatched] = useState(false);

  const quote = useQuery({
    queryKey: ["quote", symbol],
    queryFn: () => fetchQuote(symbol, exchange),
    enabled: Boolean(symbol),
    refetchInterval: 15_000,
  });
  const history = useQuery({
    queryKey: ["history", symbol, range, exchange],
    queryFn: () => fetchHistory(symbol, range, exchange),
    enabled: Boolean(symbol),
  });
  const fundamentals = useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: () => fetchFundamentals(symbol),
    enabled: Boolean(symbol) && tab === "fundamentals",
    retry: false,
  });
  const filings = useQuery({
    queryKey: ["filings", symbol],
    queryFn: () => fetchFilings(symbol),
    enabled: Boolean(symbol) && tab === "filings",
    retry: false,
  });
  const shareholding = useQuery({
    queryKey: ["shareholding", symbol],
    queryFn: () => fetchShareholding(symbol),
    enabled: Boolean(symbol) && tab === "shareholding",
    retry: false,
  });
  const news = useQuery({
    queryKey: ["news", symbol],
    queryFn: () => fetchStockNews(symbol, quote.data?.name),
    enabled: Boolean(symbol) && tab === "news",
    retry: false,
  });
  const score = useQuery({
    queryKey: ["score", symbol, exchange],
    queryFn: () => fetchStockScore(symbol, exchange),
    enabled: Boolean(symbol) && tab === "score",
    retry: false,
  });

  const price = quote.data;
  const up = (price?.day_change_percentage ?? 0) >= 0;
  const firstLoad = !quote.data && (quote.isLoading || history.isLoading);

  if (firstLoad) {
    return <MarketLoadingScreen label={`Loading ${symbol} from INDstocks`} />;
  }

  const stats = price
    ? [
        { label: "Open", value: price.day_open, icon: LogIn },
        { label: "Prev. close", value: price.prev_close, icon: LogOut },
        { label: "Day high", value: price.day_high, icon: ArrowUpToLine },
        { label: "Day low", value: price.day_low, icon: ArrowDownToLine },
        { label: "Volume", value: price.volume, icon: BarChart2, isCount: true },
        { label: "P/E ratio", value: price.pe_ratio, icon: Percent, isRatio: true },
      ]
    : [];

  const hasSnapshot = fundamentals.data?.status === "SNAPSHOT";

  return (
    <main className="mx-auto min-h-screen w-full max-w-7xl px-4 pb-10 pt-6 lg:px-8 text-(--text-primary)">
      <Link href="/stocks" className="flex items-center gap-1 text-xs font-medium text-(--text-secondary) transition-colors hover:text-(--text-primary)">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to movers
      </Link>

      {/* Hero banner */}
      <div className={`card mt-4 flex flex-wrap items-end justify-between gap-3 p-5 ${up ? "bg-(--bull-green-soft)" : "bg-(--bear-red-soft)"}`}>
        <div className="flex items-center gap-3">
          <span className={`icon-badge h-12 w-12 bg-(--surface-1) text-base font-bold ${up ? "text-(--bull-green)" : "text-(--bear-red)"}`}>
            {symbol.slice(0, 2)}
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">{symbol}</h1>
              <button
                type="button"
                onClick={() => setWatched((v) => !v)}
                aria-pressed={watched}
                aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
                className={`rounded-full p-1.5 transition-colors ${
                  watched ? "bg-(--section-gold-soft) text-(--section-gold)" : "text-(--text-muted) hover:bg-(--surface-1) hover:text-(--section-gold)"
                }`}
              >
                <Star className={`h-4 w-4 ${watched ? "fill-current" : ""}`} />
              </button>
            </div>
            <p className="text-sm text-(--text-secondary)">{price?.name || "Live INDstocks quote"} · {exchange}</p>
          </div>
        </div>
        {price && (
          <div className="text-right">
            <div className="num-tabular text-3xl font-bold">
              ₹{price.live_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </div>
            <div
              className={`num-tabular mt-0.5 inline-flex items-center gap-1 rounded-md bg-(--surface-1) px-1.5 py-0.5 text-sm font-semibold ${
                up ? "text-(--bull-green)" : "text-(--bear-red)"
              }`}
            >
              {up ? "+" : ""}
              {price.day_change.toFixed(2)} ({up ? "+" : ""}
              {price.day_change_percentage.toFixed(2)}%)
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Main column: tabs + chart/fundamentals/guidance */}
        <div className="lg:col-span-8">
          <div className="flex gap-1.5 border-b border-(--border-subtle)">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-semibold transition-colors ${
                    active ? "border-(--section-stocks) text-(--section-stocks)" : "border-transparent text-(--text-secondary) hover:text-(--text-primary)"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              );
            })}
          </div>

          {tab === "overview" && (
            <>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {RANGES.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setRange(item)}
                    className={`nav-pill px-3.5 py-1.5 text-xs font-semibold ${
                      range === item
                        ? "bg-(--section-stocks) text-white"
                        : "bg-(--surface-2) text-(--text-secondary) hover:bg-(--surface-3)"
                    }`}
                  >
                    {item.toUpperCase()}
                  </button>
                ))}
              </div>

              <section className="card mt-3 p-4">
                {quote.isLoading && <div className="skeleton h-72 w-full" />}
                {quote.isError && (
                  <p className="text-sm text-(--bear-red)">
                    {quote.error instanceof Error ? quote.error.message : "Quote unavailable."}
                  </p>
                )}
                {history.isLoading && !quote.isLoading && <div className="skeleton h-72 w-full" />}
                {history.isError && (
                  <p className="mt-3 text-sm text-(--bear-red)">
                    {history.error instanceof Error ? history.error.message : "Chart unavailable."}
                  </p>
                )}
                {history.data && <PriceChart candles={history.data.candles} />}
              </section>
            </>
          )}

          {tab === "score" && (
            <div className="mt-4">
              {score.isLoading && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="skeleton h-32 w-full" />
                  ))}
                </div>
              )}
              {score.isError && (
                <div className="card-row flex items-center gap-2 p-4 text-sm text-(--bear-red)">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  {score.error instanceof Error ? score.error.message : "Score unavailable."}
                </div>
              )}
              {score.data && score.data.status === "DATA_UNAVAILABLE" && (
                <div className="card-row flex items-start gap-2.5 p-4 text-sm">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
                  <div>
                    <p className="font-semibold text-(--text-primary)">Data unavailable</p>
                    <p className="mt-1 text-xs text-(--text-secondary)">
                      {score.data.message || `${symbol} could not be scored right now.`}
                    </p>
                  </div>
                </div>
              )}
              {score.data && score.data.status === "OK" && (
                <>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {SCORE_BLOCKS.map((block) => (
                      <ScoreRing key={block.key} label={block.label} score={score.data![block.key]?.score ?? null} />
                    ))}
                  </div>

                  <div className="card mt-4 p-5">
                    <div className="flex items-center justify-between gap-3">
                      <h2 className="text-sm font-bold text-(--text-primary)">Overall score</h2>
                      <span className="num-tabular text-2xl font-bold text-(--text-primary)">
                        {score.data.overall != null ? Math.round(score.data.overall) : "—"}
                        <span className="text-sm font-normal text-(--text-secondary)">/100</span>
                      </span>
                    </div>
                    {score.data.explanation && (
                      <p className="mt-2 text-sm leading-relaxed text-(--text-secondary)">{score.data.explanation}</p>
                    )}
                  </div>

                  <div className="mt-4 space-y-3">
                    {SCORE_BLOCKS.map((block) => {
                      const data: ScoreBlock | undefined = score.data![block.key];
                      if (!data) return null;
                      return (
                        <div key={block.key} className="card p-4">
                          <h3 className="text-xs font-bold uppercase tracking-wide text-(--text-secondary)">
                            Why this {block.label.toLowerCase()} score
                          </h3>
                          <div className="mt-2.5 space-y-2">
                            {data.inputs.map((input) => (
                              <div key={input.label} className="flex items-center justify-between gap-3 text-xs">
                                <span className="text-(--text-secondary)">{input.label}</span>
                                <span className="flex items-center gap-2">
                                  <span className="num-tabular font-semibold text-(--text-primary)">
                                    {input.value != null ? `${input.value}${input.unit === "pctile" ? " pctile" : input.unit}` : "Data unavailable"}
                                  </span>
                                  {input.benchmark != null && (
                                    <span className="text-(--text-muted)">
                                      vs {input.benchmark}
                                      {input.unit === "pctile" ? " pctile" : input.unit} ({input.benchmark_label})
                                    </span>
                                  )}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {score.data.valuation_note && (
                    <p className="mt-3 text-[11px] text-(--text-muted)">{score.data.valuation_note}</p>
                  )}
                </>
              )}
            </div>
          )}

          {tab === "fundamentals" && (
            <div className="mt-4">
              {fundamentals.isLoading && (
                <div className="space-y-2.5">
                  <div className="skeleton h-20 w-full" />
                  <div className="skeleton h-20 w-full" />
                </div>
              )}
              {fundamentals.isError && (
                <div className="card-row flex items-center gap-2 p-4 text-sm text-(--bear-red)">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  {fundamentals.error instanceof Error ? fundamentals.error.message : "Fundamentals unavailable."}
                </div>
              )}
              {fundamentals.data && !hasSnapshot && (
                <div className="card-row flex items-start gap-2.5 p-4 text-sm">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
                  <div>
                    <p className="font-semibold text-(--text-primary)">No sourced fundamental snapshot stored for {symbol}.</p>
                    <p className="mt-1 text-xs text-(--text-secondary)">
                      {fundamentals.data.message || "Ratios are ingested from cited filings, not guessed by the model."}
                    </p>
                  </div>
                </div>
              )}
              {fundamentals.data && hasSnapshot && (
                <div className="card p-5">
                  <div className="flex items-center gap-2.5">
                    <span className="icon-badge h-9 w-9 bg-(--bull-green-soft) text-(--bull-green)">
                      <ShieldCheck className="h-4.5 w-4.5" />
                    </span>
                    <div>
                      <h2 className="text-sm font-bold text-(--text-primary)">Sourced fundamentals</h2>
                      <p className="text-[11px] text-(--text-secondary)">As of {fundamentals.data.data_date?.slice(0, 10)}</p>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-2.5">
                    <div className="card-row p-3">
                      <div className="text-[11px] text-(--text-secondary)">ROE</div>
                      <div className="num-tabular mt-0.5 text-sm font-semibold text-(--text-primary)">
                        {fundamentals.data.roe_pct != null ? `${fundamentals.data.roe_pct}%` : "—"}
                      </div>
                    </div>
                    <div className="card-row p-3">
                      <div className="text-[11px] text-(--text-secondary)">EPS</div>
                      <div className="num-tabular mt-0.5 text-sm font-semibold text-(--text-primary)">
                        {fundamentals.data.eps != null ? `₹${fundamentals.data.eps}` : "—"}
                      </div>
                    </div>
                  </div>
                  {fundamentals.data.source_url && (
                    <a
                      href={fundamentals.data.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-(--section-portfolio) hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" /> Source: {fundamentals.data.source_name}
                    </a>
                  )}
                </div>
              )}
            </div>
          )}

          {tab === "filings" && (
            <div className="mt-4">
              {filings.isLoading && (
                <div className="space-y-2.5">
                  <div className="skeleton h-16 w-full" />
                  <div className="skeleton h-16 w-full" />
                  <div className="skeleton h-16 w-full" />
                </div>
              )}
              {filings.isError && (
                <div className="card-row flex items-center gap-2 p-4 text-sm text-(--bear-red)">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  {filings.error instanceof Error ? filings.error.message : "Filings unavailable."}
                </div>
              )}
              {filings.data && filings.data.status === "DATA_UNAVAILABLE" && (
                <div className="card-row flex items-start gap-2.5 p-4 text-sm">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
                  <div>
                    <p className="font-semibold text-(--text-primary)">Data unavailable</p>
                    <p className="mt-1 text-xs text-(--text-secondary)">
                      NSE corporate announcements could not be fetched for {symbol} right now.
                    </p>
                  </div>
                </div>
              )}
              {filings.data && filings.data.filings.length > 0 && (
                <div className="card divide-y divide-(--border-subtle) overflow-hidden">
                  {filings.data.filings.map((item, index) => (
                    <div key={`${item.announced_at}-${index}`} className="flex items-start gap-3 p-4">
                      <span className="icon-badge mt-0.5 h-8 w-8 shrink-0 bg-(--section-research-soft) text-(--section-research)">
                        <Megaphone className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-(--surface-3) px-2 py-0.5 text-[11px] font-semibold text-(--text-secondary)">
                            {item.category}
                          </span>
                          <span className="text-[11px] text-(--text-muted)">
                            {item.announced_at ? new Date(item.announced_at).toLocaleDateString("en-IN") : "Date unavailable"}
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-(--text-primary)">{item.subject}</p>
                        {item.attachment_url && (
                          <a
                            href={item.attachment_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-1.5 flex items-center gap-1 text-xs font-semibold text-(--section-portfolio) hover:underline"
                          >
                            <ExternalLink className="h-3 w-3" /> View filing
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "news" && (
            <div className="mt-4">
              {news.isLoading && (
                <div className="space-y-2.5">
                  <div className="skeleton h-16 w-full" />
                  <div className="skeleton h-16 w-full" />
                  <div className="skeleton h-16 w-full" />
                </div>
              )}
              {news.isError && (
                <div className="card-row flex items-center gap-2 p-4 text-sm text-(--bear-red)">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  {news.error instanceof Error ? news.error.message : "News unavailable."}
                </div>
              )}
              {news.data && news.data.status === "DATA_UNAVAILABLE" && (
                <div className="card-row flex items-start gap-2.5 p-4 text-sm">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
                  <div>
                    <p className="font-semibold text-(--text-primary)">Data unavailable</p>
                    <p className="mt-1 text-xs text-(--text-secondary)">
                      No recent news headlines could be fetched for {symbol} right now.
                    </p>
                  </div>
                </div>
              )}
              {news.data && news.data.status === "OK" && (
                <>
                  <div className="card-row mb-3 flex items-center gap-2.5 p-3.5">
                    {news.data.sentiment.label === "POSITIVE" && <TrendingUp className="h-4 w-4 text-(--bull-green)" />}
                    {news.data.sentiment.label === "NEGATIVE" && <TrendingDown className="h-4 w-4 text-(--bear-red)" />}
                    {news.data.sentiment.label === "NEUTRAL" && <Minus className="h-4 w-4 text-(--text-muted)" />}
                    <div className="text-xs text-(--text-secondary)">
                      <span
                        className={`font-semibold ${
                          news.data.sentiment.label === "POSITIVE"
                            ? "text-(--bull-green)"
                            : news.data.sentiment.label === "NEGATIVE"
                              ? "text-(--bear-red)"
                              : "text-(--text-primary)"
                        }`}
                      >
                        {news.data.sentiment.label}
                      </span>{" "}
                      news sentiment · {news.data.sentiment.positive_count} positive, {news.data.sentiment.negative_count} negative
                      out of {news.data.sentiment.total_articles} headlines — a keyword-lexicon score, not an AI sentiment model.
                    </div>
                  </div>
                  <div className="card divide-y divide-(--border-subtle) overflow-hidden">
                    {news.data.articles.map((article, index) => (
                      <a
                        key={`${article.title}-${index}`}
                        href={article.link ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="card-interactive flex items-start gap-3 p-4"
                      >
                        <span className="icon-badge mt-0.5 h-8 w-8 shrink-0 bg-(--section-chat-soft) text-(--section-chat)">
                          <Newspaper className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-(--text-primary)">{article.title}</p>
                          <div className="mt-1 flex items-center gap-2 text-[11px] text-(--text-muted)">
                            <span>{article.source_name}</span>
                            {article.published_at && (
                              <>
                                <span>·</span>
                                <span>{new Date(article.published_at).toLocaleDateString("en-IN")}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </a>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {tab === "shareholding" && (
            <div className="mt-4">
              {shareholding.isLoading && (
                <div className="space-y-2.5">
                  <div className="skeleton h-14 w-full" />
                  <div className="skeleton h-14 w-full" />
                </div>
              )}
              {shareholding.isError && (
                <div className="card-row flex items-center gap-2 p-4 text-sm text-(--bear-red)">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  {shareholding.error instanceof Error ? shareholding.error.message : "Shareholding unavailable."}
                </div>
              )}
              {shareholding.data && shareholding.data.status === "DATA_UNAVAILABLE" && (
                <div className="card-row flex items-start gap-2.5 p-4 text-sm">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
                  <div>
                    <p className="font-semibold text-(--text-primary)">Data unavailable</p>
                    <p className="mt-1 text-xs text-(--text-secondary)">
                      NSE shareholding pattern could not be fetched for {symbol} right now.
                    </p>
                  </div>
                </div>
              )}
              {shareholding.data && shareholding.data.quarters.length > 0 && (
                <div className="card p-5">
                  <div className="flex items-center gap-4 text-[11px] text-(--text-secondary)">
                    {SHAREHOLDING_SEGMENTS.map((segment) => (
                      <span key={segment.key} className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: segment.color }} />
                        {segment.label}
                      </span>
                    ))}
                  </div>
                  <div className="mt-4 space-y-3">
                    {shareholding.data.quarters.map((quarter, index) => (
                      <div key={`${quarter.period_end}-${index}`}>
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-(--text-primary)">
                            {quarter.period_end ? new Date(quarter.period_end).toLocaleDateString("en-IN", { month: "short", year: "numeric" }) : "Period unavailable"}
                          </span>
                          {quarter.promoter_pledge_pct != null && (
                            <span className={`font-semibold ${quarter.promoter_pledge_pct > 0 ? "text-(--bear-red)" : "text-(--bull-green)"}`}>
                              Pledge {quarter.promoter_pledge_pct}%
                            </span>
                          )}
                        </div>
                        <div className="mt-1.5 flex h-3 w-full overflow-hidden rounded-full bg-(--surface-3)">
                          {SHAREHOLDING_SEGMENTS.map((segment) => {
                            const value = quarter[segment.key];
                            if (value == null) return null;
                            return (
                              <div
                                key={segment.key}
                                style={{ width: `${value}%`, backgroundColor: segment.color }}
                                title={`${segment.label}: ${value}%`}
                              />
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "guidance" && (
            <div className="mt-4">
              <AgentGuidance symbols={[symbol]} title={`Agent view on ${symbol}`} />
            </div>
          )}
        </div>

        {/* Sidebar: key facts, always visible */}
        <aside className="lg:col-span-4">
          <div className="card sticky top-20 p-5">
            <h2 className="text-xs font-bold uppercase tracking-wide text-(--text-secondary)">Key facts</h2>
            <div className="mt-3 grid grid-cols-2 gap-2.5">
              {stats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div key={stat.label} className="card-row p-3">
                    <div className="flex items-center gap-1.5 text-[11px] text-(--text-secondary)">
                      <Icon className="h-3 w-3" /> {stat.label}
                    </div>
                    <div className="num-tabular mt-1 text-sm font-semibold text-(--text-primary)">
                      {stat.value == null
                        ? "—"
                        : stat.isCount
                          ? stat.value.toLocaleString("en-IN")
                          : stat.isRatio
                            ? stat.value.toFixed(2)
                            : `₹${stat.value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`}
                    </div>
                  </div>
                );
              })}
              {price?.market_cap_cr != null && (
                <div className="card-row col-span-2 p-3">
                  <div className="flex items-center gap-1.5 text-[11px] text-(--text-secondary)">
                    <Building2 className="h-3 w-3" /> Market cap
                  </div>
                  <div className="num-tabular mt-1 text-sm font-semibold text-(--text-primary)">
                    ₹{price.market_cap_cr.toLocaleString("en-IN")} Cr
                  </div>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setTab("guidance")}
              className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-(--section-research) py-2.5 text-xs font-semibold text-white transition-colors hover:brightness-95"
            >
              <Sparkles className="h-3.5 w-3.5" />
              Get AI guidance
            </button>
            <p className="mt-2 text-center text-[11px] text-(--text-muted)">Research view only · not an order placement screen</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
