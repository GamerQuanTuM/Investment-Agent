"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Scale, X } from "lucide-react";
import { compareStocks, fetchTrending } from "@/lib/api";
import { CompareResult } from "@/lib/types";
import { ScoreRing } from "@/components/ScoreRing";
import { StockSearch } from "@/components/StockSearch";

const MAX_SYMBOLS = 5;

const SCORE_BLOCKS: { key: "quality" | "valuation" | "momentum" | "risk"; label: string }[] = [
  { key: "quality", label: "Quality" },
  { key: "valuation", label: "Valuation" },
  { key: "momentum", label: "Momentum" },
  { key: "risk", label: "Risk" },
];

export default function ComparePage() {
  const [symbols, setSymbols] = useState<string[]>(["TCS", "INFY"]);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trending = useQuery({ queryKey: ["trending", 0], queryFn: () => fetchTrending(0), retry: false });
  const popularSymbols = (trending.data?.items ?? []).slice(0, 8);

  const addSymbol = (symbol: string) => {
    const trimmed = symbol.trim().toUpperCase();
    if (!trimmed || symbols.includes(trimmed) || symbols.length >= MAX_SYMBOLS) return;
    setSymbols([...symbols, trimmed]);
  };

  const run = async () => {
    if (symbols.length === 0) return;
    setError(null);
    setBusy(true);
    try {
      setResult(await compareStocks(symbols));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not compare these symbols. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <div className="flex items-center gap-2.5">
        <span className="icon-badge h-9 w-9 bg-(--section-research-soft) text-(--section-research)">
          <Scale className="h-4.5 w-4.5" />
        </span>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-(--text-primary)">Compare stocks</h1>
          <p className="text-sm text-(--text-secondary)">
            Side-by-side F2 scores (Quality/Valuation/Momentum/Risk) for up to {MAX_SYMBOLS} symbols.
          </p>
        </div>
      </div>

      <div className="card mt-5 p-5">
        {symbols.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            {symbols.map((symbol) => (
              <span
                key={symbol}
                className="nav-pill flex items-center gap-1.5 bg-(--surface-2) px-3 py-1.5 text-xs font-semibold text-(--text-primary)"
              >
                {symbol}
                <button
                  type="button"
                  onClick={() => setSymbols(symbols.filter((s) => s !== symbol))}
                  aria-label={`Remove ${symbol}`}
                  className="text-(--text-muted) hover:text-(--bear-red)"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {symbols.length < MAX_SYMBOLS && (
          <div className="mt-3">
            <StockSearch onSelect={(stock) => addSymbol(stock.symbol)} />
            {popularSymbols.length > 0 && (
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-semibold text-(--text-muted)">Today&apos;s movers:</span>
                {popularSymbols.map((item) => (
                  <button
                    key={item.symbol}
                    type="button"
                    onClick={() => addSymbol(item.symbol)}
                    disabled={symbols.includes(item.symbol)}
                    className="nav-pill px-2.5 py-1 text-[11px] font-semibold text-(--text-secondary) hover:bg-(--surface-3) disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {item.symbol}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={() => void run()}
          disabled={busy || symbols.length === 0}
          className="mt-4 rounded-xl bg-(--section-research) px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Comparing…" : "Compare"}
        </button>
        {error && <p className="mt-3 text-sm text-(--bear-red)">{error}</p>}
      </div>

      {result && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[640px] border-separate border-spacing-0">
            <thead>
              <tr>
                <th className="w-32 px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-(--text-muted)">
                  Metric
                </th>
                {result.items.map((item) => (
                  <th key={item.symbol} className="px-3 py-2 text-center text-sm font-bold text-(--text-primary)">
                    {item.symbol}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-3 py-3 text-xs font-semibold text-(--text-secondary)">Overall</td>
                {result.items.map((item) => (
                  <td key={item.symbol} className="px-3 py-3 text-center">
                    <ScoreRing label="" score={item.status === "OK" ? item.overall ?? null : null} size={64} />
                  </td>
                ))}
              </tr>
              {SCORE_BLOCKS.map((block) => (
                <tr key={block.key} className="card-row">
                  <td className="px-3 py-3 text-xs font-semibold text-(--text-secondary)">{block.label}</td>
                  {result.items.map((item) => {
                    const score = item.status === "OK" ? item[block.key]?.score ?? null : null;
                    return (
                      <td
                        key={item.symbol}
                        className={`num-tabular px-3 py-3 text-center text-sm font-bold ${
                          score == null
                            ? "text-(--text-muted)"
                            : score >= 70
                              ? "text-(--bull-green)"
                              : score >= 40
                                ? "text-(--section-gold)"
                                : "text-(--bear-red)"
                        }`}
                      >
                        {score == null ? "—" : Math.round(score)}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <td className="px-3 py-3 text-xs font-semibold text-(--text-secondary)">Status</td>
                {result.items.map((item) => (
                  <td key={item.symbol} className="px-3 py-3 text-center text-xs text-(--text-secondary)">
                    {item.status === "OK" ? "OK" : "Data unavailable"}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
