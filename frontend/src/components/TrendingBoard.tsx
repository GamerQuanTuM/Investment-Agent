"use client";

import Link from "next/link";
import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, TrendingUp } from "lucide-react";
import { fetchTrending } from "@/lib/api";
import { StockQuote } from "@/lib/types";

function formatInr(value: number) {
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function MoverRow({ quote }: { quote: StockQuote }) {
  const up = quote.day_change_percentage >= 0;
  return (
    <Link
      href={`/stocks/${quote.symbol}`}
      className="card-row card-interactive flex items-center justify-between gap-3 px-3.5 py-3"
    >
      <div className="flex items-center gap-2.5">
        <span className={`icon-badge h-8 w-8 text-xs font-bold ${up ? "bg-(--bull-green-soft) text-(--bull-green)" : "bg-(--bear-red-soft) text-(--bear-red)"}`}>
          {quote.symbol.slice(0, 2)}
        </span>
        <div>
          <div className="font-bold text-sm text-(--text-primary)">{quote.symbol}</div>
          <div className="text-[11px] text-(--text-secondary)">{quote.name}</div>
        </div>
      </div>
      <div className="text-right">
        <div className="num-tabular text-sm font-semibold text-(--text-primary)">
          ₹{formatInr(quote.live_price)}
        </div>
        <div className={`num-tabular text-xs font-semibold ${up ? "text-(--bull-green)" : "text-(--bear-red)"}`}>
          {up ? "+" : ""}
          {quote.day_change_percentage.toFixed(2)}%
        </div>
      </div>
    </Link>
  );
}

export function TrendingBoard() {
  const [page, setPage] = useState(0);
  const query = useInfiniteQuery({
    queryKey: ["trending"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => fetchTrending(pageParam),
    getNextPageParam: (last) => last.next_offset ?? undefined,
    retry: false,
    refetchInterval: (query) => (query.state.data?.pages[0]?.pending ? 2000 : false),
  });

  const current = query.data?.pages[page];
  const canGoBack = page > 0;
  const canGoForward = page + 1 < (query.data?.pages.length ?? 0) || Boolean(query.hasNextPage);

  const onNext = async () => {
    if (page + 1 < (query.data?.pages.length ?? 0)) {
      setPage((value) => value + 1);
      return;
    }
    if (!query.hasNextPage || query.isFetchingNextPage) return;
    await query.fetchNextPage();
    setPage((value) => value + 1);
  };

  return (
    <section className="card p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-9 w-9 bg-(--section-stocks-soft) text-(--section-stocks)">
            <TrendingUp className="h-4.5 w-4.5" />
          </span>
          <div>
            <h2 className="text-sm font-bold text-(--text-primary)">Trending on NSE</h2>
            <p className="mt-0.5 text-xs text-(--text-secondary)">
              Live session movers, five at a time
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Previous stocks"
            disabled={!canGoBack}
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            className="rounded-lg border border-(--border-subtle) bg-(--surface-2) p-2 text-(--text-secondary) transition-colors hover:bg-(--surface-3) disabled:opacity-40 disabled:hover:bg-(--surface-2)"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label="Next stocks"
            disabled={!canGoForward || query.isFetchingNextPage}
            onClick={() => void onNext()}
            className="rounded-lg border border-(--border-subtle) bg-(--surface-2) p-2 text-(--text-secondary) transition-colors hover:bg-(--surface-3) disabled:opacity-40 disabled:hover:bg-(--surface-2)"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {query.isLoading && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-16" />
          ))}
        </div>
      )}
      {query.isError && (
        <p className="text-sm text-(--bear-red)">
          {query.error instanceof Error ? query.error.message : "Live prices are unavailable."}
        </p>
      )}
      {current && (
        <div className="flex flex-col gap-2">
          {current.items.map((quote) => (
            <MoverRow key={quote.symbol} quote={quote} />
          ))}
          {current.items.length === 0 && (
            <p className="text-sm text-(--text-secondary)">No live movers in this page.</p>
          )}
        </div>
      )}
      {query.isFetchingNextPage && (
        <p className="mt-3 text-xs text-(--text-secondary)">Loading the next five…</p>
      )}
    </section>
  );
}
