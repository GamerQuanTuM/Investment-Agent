"use client";

import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/Header";
import { BrokerVaultCard } from "@/components/BrokerVaultCard";
import { MarketLoadingScreen } from "@/components/MarketLoadingScreen";
import { fetchBrokerVault, fetchHealthStatus, fetchIndices, fetchMarketStatus, fetchTrending, refreshMarket } from "@/lib/api";
import Link from "next/link";
import {
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Wallet,
  LineChart,
  Banknote,
  Layers,
  FlaskConical,
  Link2Off,
  CandlestickChart,
  PiggyBank,
  Sparkles,
  Sun,
  Moon,
  Sunrise,
} from "lucide-react";

function Greeting() {
  const hour = new Date().getHours();
  const { text, Icon } =
    hour < 12
      ? { text: "Good morning", Icon: Sunrise }
      : hour < 17
        ? { text: "Good afternoon", Icon: Sun }
        : { text: "Good evening", Icon: Moon };
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-5 w-5 text-(--section-gold)" />
      <h1 className="text-lg font-bold tracking-tight text-(--text-primary)">{text}, Investor</h1>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  subTone,
  color,
  soft,
  href,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  subTone?: "up" | "down" | "neutral";
  color: string;
  soft: string;
  href?: string;
}) {
  const Wrapper = href ? Link : "div";
  return (
    <Wrapper href={href as string} className="card card-interactive block p-4">
      <div className="flex items-center gap-2.5">
        <span className="icon-badge h-9 w-9" style={{ backgroundColor: soft, color }}>
          <Icon className="h-4.5 w-4.5" />
        </span>
        <span className="text-xs font-semibold text-(--text-secondary)">{label}</span>
      </div>
      <div className="num-tabular mt-3 text-xl font-bold text-(--text-primary)">{value}</div>
      {sub && (
        <div
          className={`num-tabular mt-1 text-xs font-semibold ${
            subTone === "up" ? "text-(--bull-green)" : subTone === "down" ? "text-(--bear-red)" : "text-(--text-secondary)"
          }`}
        >
          {sub}
        </div>
      )}
    </Wrapper>
  );
}

const QUICK_ACTIONS = [
  { href: "/stocks", label: "Stocks", icon: CandlestickChart, color: "var(--section-stocks)", soft: "var(--section-stocks-soft)" },
  { href: "/research", label: "Research", icon: FlaskConical, color: "var(--section-research)", soft: "var(--section-research-soft)" },
  { href: "/sip", label: "SIP", icon: PiggyBank, color: "var(--section-sip)", soft: "var(--section-sip-soft)" },
  { href: "/chat", label: "Ask AI", icon: Sparkles, color: "var(--section-chat)", soft: "var(--section-chat-soft)" },
];

export default function InvestmentCockpitPage() {
  const client = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealthStatus, retry: false });
  const broker = useQuery({ queryKey: ["portfolio"], queryFn: fetchBrokerVault, retry: false });
  const marketStatus = useQuery({ queryKey: ["market-status"], queryFn: fetchMarketStatus, retry: false });
  const indices = useQuery({
    queryKey: ["indices"],
    queryFn: fetchIndices,
    retry: false,
  });
  const trending = useInfiniteQuery({
    queryKey: ["trending"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => fetchTrending(pageParam),
    getNextPageParam: (last) => last.next_offset ?? undefined,
    retry: false,
    refetchInterval: (query) => (query.state.data?.pages[0]?.pending ? 2000 : false),
  });

  const refresh = async () => {
    setSyncing(true);
    try {
      await refreshMarket();
    } catch {
      // Backend refresh is best-effort; fall through to re-fetching whatever is cached.
    }
    await client.invalidateQueries();
    setSyncing(false);
  };

  const firstPage = trending.data?.pages[0];
  const waitingOnIndstocks =
    !trending.isError &&
    (trending.isLoading || Boolean(firstPage?.pending && firstPage.items.length === 0));
  const loadingLabel =
    firstPage?.universe
      ? `Scanning NSE prices ${firstPage.scanned ?? 0} of ${firstPage.universe}`
      : "Fetching live NSE prices";

  const b = broker.data;
  const pnlUp = (b?.day_change_pnl ?? 0) >= 0;
  const money = (v: number | null | undefined) => (v == null ? "—" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`);
  const nifty = indices.data?.items.find((i) => i.name.toUpperCase().includes("NIFTY"));
  const niftyUp = (nifty?.day_change_percentage ?? 0) >= 0;
  const brokerNotConfigured = marketStatus.data?.indstocks_configured === false;

  return (
    <div className="flex min-h-screen flex-col bg-(--bg-base) font-sans text-(--text-primary)">
      {waitingOnIndstocks && <MarketLoadingScreen label={loadingLabel} />}
      <Header
        health={health.data ?? null}
        broker={broker.data ?? null}
        indices={indices.data?.items ?? []}
        isRefreshing={syncing}
        onRefresh={() => void refresh()}
      />

      <main className="mx-auto w-full max-w-7xl flex-1 p-4 lg:px-8 lg:py-6">
        <Greeting />

        {/* Quick actions */}
        <div className="mt-3 grid grid-cols-4 gap-2.5">
          {QUICK_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <Link
                key={action.href}
                href={action.href}
                className="card card-interactive flex flex-col items-center gap-1.5 py-3.5 text-center"
              >
                <span className="icon-badge h-9 w-9" style={{ backgroundColor: action.soft, color: action.color }}>
                  <Icon className="h-4.5 w-4.5" />
                </span>
                <span className="text-xs font-semibold text-(--text-primary)">{action.label}</span>
              </Link>
            );
          })}
        </div>

        {/* Stat strip */}
        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            icon={Wallet}
            label="Portfolio value"
            value={money(b?.portfolio_total_value)}
            sub={b?.day_change_pnl != null ? `${pnlUp ? "+" : ""}${money(b.day_change_pnl)} today (${b.day_change_pct ?? 0}%)` : undefined}
            subTone={pnlUp ? "up" : "down"}
            color="var(--section-portfolio)"
            soft="var(--section-portfolio-soft)"
          />
          <StatCard
            icon={Banknote}
            label="Cash available"
            value={money(b?.cash_available)}
            sub="Read-only broker sync"
            subTone="neutral"
            color="var(--section-sip)"
            soft="var(--section-sip-soft)"
          />
          <StatCard
            icon={Layers}
            label="Demat holdings"
            value={`${b?.holdings.length ?? 0} stocks`}
            sub="Across NSE cash segment"
            subTone="neutral"
            color="var(--section-stocks)"
            soft="var(--section-stocks-soft)"
            href="/stocks"
          />
          <StatCard
            icon={LineChart}
            label="NIFTY 50"
            value={nifty?.live_price.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—"}
            sub={nifty ? `${niftyUp ? "+" : ""}${nifty.day_change_percentage.toFixed(2)}% today` : undefined}
            subTone={niftyUp ? "up" : "down"}
            color="var(--section-gold)"
            soft="var(--section-gold-soft)"
            href="/stocks"
          />
        </div>

        {/* Broker connection empty state */}
        {brokerNotConfigured && (
          <div className="card mt-4 flex flex-col items-start gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="icon-badge h-9 w-9 bg-(--surface-3) text-(--text-muted)">
                <Link2Off className="h-4.5 w-4.5" />
              </span>
              <div>
                <p className="text-sm font-semibold text-(--text-primary)">No broker connected</p>
                <p className="text-xs text-(--text-secondary)">
                  Configure INDstocks credentials on the backend to sync live Demat holdings and cash balance here.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Main grid: holdings + watchlist */}
        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <BrokerVaultCard
              broker={broker.data ?? null}
              error={broker.error instanceof Error ? broker.error.message : null}
              loading={broker.isLoading}
            />
          </div>

          <div className="flex flex-col gap-5 lg:col-span-5">
            <Link
              href="/research"
              className="card card-interactive flex items-center gap-3 bg-(--section-research-soft) p-4"
            >
              <span className="icon-badge h-10 w-10 bg-(--surface-1) text-(--section-research)">
                <FlaskConical className="h-5 w-5" />
              </span>
              <div className="flex-1">
                <p className="text-sm font-bold text-(--text-primary)">Run the deep research pipeline</p>
                <p className="text-xs text-(--text-secondary)">Multi-agent screening, dialectic stress-test &amp; evidence partitioning</p>
              </div>
              <ArrowRight className="h-4 w-4 text-(--section-research)" />
            </Link>

            <section className="card p-5">
              <div className="flex items-center gap-2.5">
                <span className="icon-badge h-9 w-9 bg-(--section-gold-soft) text-(--section-gold)">
                  <LineChart className="h-4.5 w-4.5" />
                </span>
                <h2 className="text-sm font-bold text-(--text-primary)">Index pulse</h2>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2.5">
                {(indices.data?.items ?? []).map((item) => {
                  const up = item.day_change_percentage >= 0;
                  return (
                    <div key={item.name} className="card-row p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold uppercase tracking-wide text-(--text-muted)">{item.bucket || "Index"}</span>
                        {up ? <TrendingUp className="h-3.5 w-3.5 text-(--bull-green)" /> : <TrendingDown className="h-3.5 w-3.5 text-(--bear-red)" />}
                      </div>
                      <div className="mt-1 text-xs font-semibold text-(--text-primary)">{item.name}</div>
                      <div className="num-tabular text-base font-bold text-(--text-primary)">
                        {item.live_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                      </div>
                      <div className={`text-xs font-bold ${up ? "text-(--bull-green)" : "text-(--bear-red)"}`}>
                        {up ? "+" : ""}
                        {item.day_change_percentage.toFixed(2)}%
                      </div>
                    </div>
                  );
                })}
                {indices.data?.items.length === 0 && (
                  <p className="col-span-full text-sm text-(--text-secondary)">Indices unavailable.</p>
                )}
              </div>
            </section>

            <section className="card p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="icon-badge h-9 w-9 bg-(--section-stocks-soft) text-(--section-stocks)">
                    <TrendingUp className="h-4.5 w-4.5" />
                  </span>
                  <h2 className="text-sm font-bold text-(--text-primary)">Biggest NSE moves</h2>
                </div>
                <Link href="/stocks" className="flex items-center gap-1 text-xs font-semibold text-(--section-stocks) hover:underline">
                  All stocks <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
              <div className="mt-3 space-y-2">
                {(firstPage?.items ?? []).slice(0, 5).map((item) => {
                  const up = item.day_change_percentage >= 0;
                  return (
                    <Link key={item.symbol} href={`/stocks/${item.symbol}`} className="card-row card-interactive flex items-center justify-between px-3.5 py-2.5">
                      <span className="font-semibold text-(--text-primary)">{item.symbol}</span>
                      <span className={`num-tabular text-sm font-semibold ${up ? "text-(--bull-green)" : "text-(--bear-red)"}`}>
                        ₹{item.live_price.toLocaleString("en-IN")} · {up ? "+" : ""}{item.day_change_percentage.toFixed(2)}%
                      </span>
                    </Link>
                  );
                })}
                {(firstPage?.items ?? []).length === 0 && (
                  <p className="text-sm text-(--text-secondary)">No live movers yet.</p>
                )}
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
