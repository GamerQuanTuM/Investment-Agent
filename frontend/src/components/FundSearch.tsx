"use client";

import { useEffect, useRef, useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { searchFunds } from "@/lib/api";
import { FundSummary } from "@/lib/types";

function isFundSummary(item: unknown): item is FundSummary {
  return typeof item === "object" && item !== null && "fund_house" in item;
}

// A beginner has no way to know a fund's name to even start typing it, so the search box
// shows these before any input -- real, verified scheme codes (checked live against
// mfapi.in) spanning the common categories, not a claim that these are the "best" funds.
// This is a starting point for discovery, same spirit as the "Today's movers" quick-add
// row on the Compare page.
const POPULAR_FUNDS: { scheme_code: string; name: string }[] = [
  { scheme_code: "119598", name: "SBI Large Cap Fund - Direct Plan - Growth" },
  { scheme_code: "118955", name: "HDFC Flexi Cap Fund - Direct Plan - Growth Option" },
  { scheme_code: "122639", name: "Parag Parikh Flexi Cap Fund - Direct Plan - Growth" },
  { scheme_code: "120716", name: "UTI Nifty 50 Index Fund - Direct Plan - Growth" },
  { scheme_code: "118825", name: "Mirae Asset Large Cap Fund - Direct Plan - Growth" },
  { scheme_code: "120828", name: "Quant Small Cap Fund - Direct Plan - Growth Option" },
];

interface FundSearchProps {
  onSelect: (scheme: { scheme_code: string; name: string }) => void;
  placeholder?: string;
}

export function FundSearch({ onSelect, placeholder = "Search by fund name, e.g. SBI Bluechip" }: FundSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<(FundSummary | { scheme_code: string; scheme_name: string })[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const result = await searchFunds(trimmed);
        setResults(result.items);
        setOpen(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Fund search failed.");
        setResults([]);
      } finally {
        setBusy(false);
      }
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

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
            if (value.trim().length < 2) {
              setResults([]);
              setOpen(false);
            }
          }}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder}
          aria-label="Search mutual funds"
          className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-1) py-2.5 pl-9 pr-9 text-sm text-(--text-primary) placeholder:text-(--text-muted) focus:border-(--section-sip) focus:outline-none focus:ring-2 focus:ring-(--section-sip)/20"
        />
        {busy && <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-(--text-muted)" />}
      </div>

      {error && <p className="mt-1.5 text-xs text-(--bear-red)">{error}</p>}

      {open && results.length > 0 && (
        <ul className="absolute z-20 mt-1.5 max-h-72 w-full overflow-y-auto rounded-xl border border-(--border-subtle) bg-(--surface-1) py-1.5 shadow-(--shadow-card)">
          {results.map((item) => {
            const name = isFundSummary(item) ? item.name : item.scheme_name;
            const subtitle = isFundSummary(item)
              ? [item.fund_house, item.plan, item.option].filter(Boolean).join(" · ")
              : "Unclassified result";
            return (
              <li key={item.scheme_code}>
                <button
                  type="button"
                  onClick={() => {
                    onSelect({ scheme_code: item.scheme_code, name });
                    setQuery(name);
                    setOpen(false);
                  }}
                  className="card-row flex w-full flex-col items-start gap-0.5 px-3.5 py-2.5 text-left"
                >
                  <span className="text-sm font-semibold text-(--text-primary)">{name}</span>
                  <span className="text-xs text-(--text-secondary)">{subtitle}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {open && !busy && results.length === 0 && query.trim().length >= 2 && (
        <div className="absolute z-20 mt-1.5 w-full rounded-xl border border-(--border-subtle) bg-(--surface-1) px-3.5 py-3 text-xs text-(--text-secondary) shadow-(--shadow-card)">
          No matching funds. The fund master may not be synced yet.
        </div>
      )}

      {!open && query.trim().length === 0 && (
        <div className="mt-2">
          <p className="text-[11px] font-semibold text-(--text-muted)">
            Not sure what to search? A few well-known funds to start from:
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {POPULAR_FUNDS.map((fund) => (
              <button
                key={fund.scheme_code}
                type="button"
                onClick={() => {
                  onSelect(fund);
                  setQuery(fund.name);
                }}
                className="nav-pill px-2.5 py-1 text-[11px] font-semibold text-(--text-secondary) hover:bg-(--surface-3)"
              >
                {fund.name.split(" - ")[0]}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
