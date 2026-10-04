"use client";

import { useEffect, useRef, useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { searchStocks } from "@/lib/api";

interface StockSearchProps {
  onSelect: (stock: { symbol: string; name: string }) => void;
  placeholder?: string;
  exchange?: string;
}

export function StockSearch({ onSelect, placeholder = "Search by company name or symbol…", exchange = "NSE" }: StockSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ symbol: string; name: string; exchange: string }[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = query.trim();
    if (trimmed.length < 1) {
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const result = await searchStocks(trimmed, exchange);
        setResults(result.items);
        setOpen(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Stock search failed.");
        setResults([]);
      } finally {
        setBusy(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, exchange]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-(--text-muted)" />
        <input
          type="text"
          value={query}
          onChange={(event) => {
            const value = event.target.value;
            setQuery(value);
            if (value.trim().length < 1) {
              setResults([]);
              setOpen(false);
            }
          }}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder}
          aria-label="Search stocks"
          className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-1) py-2.5 pl-9 pr-9 text-sm text-(--text-primary) placeholder:text-(--text-muted) focus:border-(--section-research) focus:outline-none focus:ring-2 focus:ring-(--section-research)/20"
        />
        {busy && <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-(--text-muted)" />}
      </div>

      {error && <p className="mt-1.5 text-xs text-(--bear-red)">{error}</p>}

      {open && results.length > 0 && (
        <ul className="absolute z-20 mt-1.5 max-h-72 w-full overflow-y-auto rounded-xl border border-(--border-subtle) bg-(--surface-1) py-1.5 shadow-(--shadow-card)">
          {results.map((item) => (
            <li key={item.symbol}>
              <button
                type="button"
                onClick={() => {
                  onSelect({ symbol: item.symbol, name: item.name });
                  setQuery("");
                  setResults([]);
                  setOpen(false);
                }}
                className="card-row flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-left"
              >
                <span className="text-sm font-semibold text-(--text-primary)">{item.symbol}</span>
                <span className="truncate text-xs text-(--text-secondary)">{item.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && !busy && results.length === 0 && query.trim().length >= 1 && (
        <div className="absolute z-20 mt-1.5 w-full rounded-xl border border-(--border-subtle) bg-(--surface-1) px-3.5 py-3 text-xs text-(--text-secondary) shadow-(--shadow-card)">
          No matching stocks.
        </div>
      )}
    </div>
  );
}
