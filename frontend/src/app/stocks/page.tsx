"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  Search,
  CandlestickChart,
  TrendingUp,
  TrendingDown,
  LayoutGrid,
  Star,
  Activity,
} from "lucide-react";
import { fetchTrending, searchStocks } from "@/lib/api";

const FILTERS = [
  { id: "all", label: "All", icon: LayoutGrid },
  { id: "gainers", label: "Top gainers", icon: TrendingUp },
  { id: "losers", label: "Top losers", icon: TrendingDown },
] as const;

export default function StocksPage() {
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sentinel = useRef<HTMLDivElement | null>(null);

  const toggleWatch = (symbol: string) => {
    setWatchlist((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  };

  const list = useInfiniteQuery({
    queryKey: ["stocks", exchange],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => fetchTrending(pageParam, exchange),
    getNextPageParam: (last) => last.next_offset ?? undefined,
    retry: false,
    enabled: submitted.length === 0,
  });

  const found = useInfiniteQuery({
    queryKey: ["search", exchange, submitted],
    initialPageParam: 0,
    queryFn: async () => ({ items: (await searchStocks(submitted, exchange)).items, next_offset: null }),
    getNextPageParam: () => undefined,
    enabled: submitted.length > 0,
    retry: false,
  });

  useEffect(() => {
    const node = sentinel.current;
    const root = scrollRef.current;
    if (!node || !root || submitted) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && list.hasNextPage && !list.isFetchingNextPage) {
          void list.fetchNextPage();
        }
      },
      { root },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [list, submitted]);

  const baseRows = submitted
    ? (found.data?.pages ?? []).flatMap((page) => page.items)
    : (list.data?.pages ?? []).flatMap((page) => page.items);

  const rows = useMemo(() => {
    if (filter === "all" || submitted) return baseRows;
    const withChange = baseRows.filter((item) => "day_change_percentage" in item);
    const sorted = [...withChange].sort((a, b) => {
      const ca = "day_change_percentage" in a ? a.day_change_percentage : 0;
      const cb = "day_change_percentage" in b ? b.day_change_percentage : 0;
      return filter === "gainers" ? cb - ca : ca - cb;
    });
    return sorted.slice(0, 24);
  }, [baseRows, filter, submitted]);

  const breadth = useMemo(() => {
    let advancing = 0;
    let declining = 0;
    for (const item of baseRows) {
      if (!("day_change_percentage" in item)) continue;
      if (item.day_change_percentage >= 0) advancing += 1;
      else declining += 1;
    }
    return { advancing, declining };
  }, [baseRows]);

  const isLoading = list.isLoading || found.isLoading;
  const isError = submitted ? found.isError : list.isError;
  const errorObj = submitted ? found.error : list.error;

  return (
    <main className="mx-auto flex h-[calc(100vh-7.5rem)] w-full max-w-7xl flex-col px-4 py-6 lg:px-8">
      {/* Fixed header: title, search, breadth, filters */}
      <div className="shrink-0">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <span className="icon-badge h-9 w-9 bg-(--section-stocks-soft) text-(--section-stocks)">
              <CandlestickChart className="h-4.5 w-4.5" />
            </span>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-(--text-primary)">Stocks</h1>
              <p className="text-sm text-(--text-secondary)">Live movers on NSE and BSE.</p>
            </div>
          </div>
          <form
            className="flex gap-2 sm:w-96"
            onSubmit={(event) => {
              event.preventDefault();
              setSubmitted(query.trim());
            }}
          >
            <div className="flex flex-1 items-center gap-2 rounded-xl border border-(--border-subtle) bg-(--surface-1) px-3 shadow-(--shadow-card) transition-colors focus-within:border-(--section-stocks) focus-within:ring-2 focus-within:ring-(--section-stocks)/25">
              <Search className="h-4 w-4 text-(--text-muted)" />
              <label htmlFor="stock-search" className="sr-only">Search stocks</label>
              <input
                id="stock-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search Reliance, TCS..."
                className="w-full bg-transparent py-2.5 text-sm text-(--text-primary) outline-none"
              />
            </div>
            <button
              className="rounded-xl bg-(--section-stocks) px-4 text-sm font-semibold text-white transition-colors hover:brightness-95"
              type="submit"
            >
              Search
            </button>
          </form>
        </div>

        {!submitted && (breadth.advancing > 0 || breadth.declining > 0) && (
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="card-row flex items-center gap-2.5 p-3">
              <span className="icon-badge h-8 w-8 bg-(--bull-green-soft) text-(--bull-green)">
                <TrendingUp className="h-4 w-4" />
              </span>
              <div>
                <div className="num-tabular text-sm font-bold text-(--text-primary)">{breadth.advancing}</div>
                <div className="text-[11px] text-(--text-secondary)">Advancing</div>
              </div>
            </div>
            <div className="card-row flex items-center gap-2.5 p-3">
              <span className="icon-badge h-8 w-8 bg-(--bear-red-soft) text-(--bear-red)">
                <TrendingDown className="h-4 w-4" />
              </span>
              <div>
                <div className="num-tabular text-sm font-bold text-(--text-primary)">{breadth.declining}</div>
                <div className="text-[11px] text-(--text-secondary)">Declining</div>
              </div>
            </div>
            <div className="card-row hidden items-center gap-2.5 p-3 sm:flex">
              <span className="icon-badge h-8 w-8 bg-(--section-gold-soft) text-(--section-gold)">
                <Activity className="h-4 w-4" />
              </span>
              <div>
                <div className="num-tabular text-sm font-bold text-(--text-primary)">{watchlist.size}</div>
                <div className="text-[11px] text-(--text-secondary)">Watchlisted</div>
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-2">
            {(["NSE", "BSE"] as const).map((venue) => (
              <button
                key={venue}
                type="button"
                onClick={() => {
                  setExchange(venue);
                  setSubmitted("");
                }}
                className={`nav-pill px-3.5 py-1.5 text-xs font-semibold ${
                  exchange === venue
                    ? "bg-(--section-stocks) text-white"
                    : "bg-(--surface-2) text-(--text-secondary) hover:bg-(--surface-3)"
                }`}
              >
                {venue}
              </button>
            ))}
          </div>
          <div className="flex gap-1.5">
            {FILTERS.map((f) => {
              const Icon = f.icon;
              const active = filter === f.id;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFilter(f.id)}
                  className={`nav-pill flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold ${
                    active ? "bg-(--section-portfolio-soft) text-(--section-portfolio)" : "text-(--text-secondary) hover:bg-(--surface-3)"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {f.label}
                </button>
              );
            })}
          </div>
        </div>

        {isError && (
          <div className="card-row mt-4 p-4 text-sm text-(--bear-red)">
            {errorObj instanceof Error ? errorObj.message : "Live prices are unavailable."}
          </div>
        )}
      </div>

      {/* Scrollable list only */}
      <div ref={scrollRef} className="card mt-4 min-h-0 flex-1 overflow-y-auto divide-y divide-(--border-subtle)">
        {isLoading &&
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="p-3.5">
              <div className="skeleton h-12 w-full" />
            </div>
          ))}

        {rows.map((item) => {
          const change = "day_change_percentage" in item ? item.day_change_percentage : null;
          const up = (change ?? 0) >= 0;
          const isWatched = watchlist.has(item.symbol);
          return (
            <div key={item.symbol} className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-(--surface-2) sm:px-5">
              <button
                type="button"
                onClick={() => toggleWatch(item.symbol)}
                aria-pressed={isWatched}
                aria-label={isWatched ? `Remove ${item.symbol} from watchlist` : `Add ${item.symbol} to watchlist`}
                className={`shrink-0 rounded-full p-1.5 transition-colors ${
                  isWatched ? "text-(--section-gold)" : "text-(--text-muted) opacity-0 group-hover:opacity-100 hover:bg-(--surface-3) hover:text-(--section-gold)"
                }`}
              >
                <Star className={`h-4 w-4 ${isWatched ? "fill-current" : ""}`} />
              </button>

              <Link href={`/stocks/${item.symbol}?exchange=${exchange}`} className="flex flex-1 items-center justify-between gap-3 min-w-0">
                <div className="flex items-center gap-3 min-w-0">
                  <span
                    className={`icon-badge h-9 w-9 shrink-0 text-xs font-bold ${
                      up ? "bg-(--bull-green-soft) text-(--bull-green)" : "bg-(--bear-red-soft) text-(--bear-red)"
                    }`}
                  >
                    {item.symbol.slice(0, 2)}
                  </span>
                  <div className="min-w-0">
                    <div className="truncate font-bold text-(--text-primary) group-hover:underline">{item.symbol}</div>
                    <div className="truncate text-xs text-(--text-secondary)">{"name" in item ? item.name : ""}</div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <div className="num-tabular text-right font-semibold text-(--text-primary)">
                    {"live_price" in item && item.live_price != null ? `₹${item.live_price.toLocaleString("en-IN")}` : "—"}
                  </div>
                  {change != null && (
                    <span
                      className={`num-tabular inline-flex w-20 items-center justify-center gap-1 rounded-full px-2 py-1 text-xs font-bold ${
                        up ? "bg-(--bull-green-soft) text-(--bull-green)" : "bg-(--bear-red-soft) text-(--bear-red)"
                      }`}
                    >
                      {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {up ? "+" : ""}
                      {change.toFixed(2)}%
                    </span>
                  )}
                </div>
              </Link>
            </div>
          );
        })}

        {rows.length === 0 && !isLoading && (
          <p className="py-8 text-center text-sm text-(--text-secondary)">No stocks found.</p>
        )}

        {/* Invisible load-more trigger, observed relative to the scroll container above */}
        {filter === "all" && !submitted && <div ref={sentinel} className="h-1" />}
      </div>

      {/* Fixed footer status */}
      {filter === "all" && !submitted && (
        <div className="shrink-0 py-1.5 text-center text-[11px] text-(--text-muted)">
          {list.isFetchingNextPage ? "Loading more stocks…" : list.hasNextPage ? "Scroll for more" : "End of this list"}
        </div>
      )}
    </main>
  );
}
