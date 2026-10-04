"use client";

import { useState } from "react";
import { Compass } from "lucide-react";
import { fetchGuidance } from "@/lib/api";
import { GuidanceNote } from "@/lib/types";

const HORIZONS = [1, 3, 5, 7];

const tone: Record<GuidanceNote["stance"], string> = {
  CONSIDER: "text-(--bull-green) bg-(--bull-green-soft)",
  WAIT: "text-(--section-gold) bg-(--section-gold-soft)",
  AVOID: "text-(--bear-red) bg-(--bear-red-soft)",
};

export function AgentGuidance({
  symbols,
  title = "Holding-span guidance",
}: {
  symbols: string[];
  title?: string;
}) {
  const [horizon, setHorizon] = useState(5);
  const [budget, setBudget] = useState(25000);
  const [notes, setNotes] = useState<GuidanceNote[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const scored = await Promise.all(symbols.map((symbol) => fetchGuidance(symbol, horizon, budget)));
      setNotes(scored);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guidance failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="card p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-9 w-9 bg-(--section-research-soft) text-(--section-research)">
            <Compass className="h-4.5 w-4.5" />
          </span>
          <div>
            <h2 className="text-sm font-bold text-(--text-primary)">{title}</h2>
            <p className="mt-0.5 text-xs text-(--text-secondary)">
              Consider, wait, or avoid from the live price, P/E, and your holding span.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void run()}
          disabled={loading || symbols.length === 0}
          className="rounded-xl bg-(--section-research) px-3 py-2 text-xs font-semibold text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Reading live quotes…" : "Score for this horizon"}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {HORIZONS.map((years) => (
          <button
            key={years}
            type="button"
            onClick={() => setHorizon(years)}
            className={`nav-pill px-3.5 py-1.5 text-xs font-semibold ${
              horizon === years
                ? "bg-(--section-research) text-white"
                : "bg-(--surface-2) text-(--text-secondary) hover:bg-(--surface-3)"
            }`}
          >
            {years}y
          </button>
        ))}
        <label className="ml-2 text-xs text-(--text-secondary)">
          Monthly budget
          <input
            type="number"
            min={1}
            step={1}
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
            className="ml-2 w-28 rounded-lg border border-(--border-subtle) bg-(--surface-2) px-2 py-1 text-(--text-primary) outline-none transition-colors focus:border-(--section-research)"
          />
        </label>
      </div>

      {error && <p className="mt-3 text-sm text-(--bear-red)">{error}</p>}
      <div className="mt-4 space-y-3">
        {loading &&
          notes.length === 0 &&
          Array.from({ length: symbols.length || 1 }).map((_, i) => <div key={i} className="skeleton h-24 w-full" />)}
        {notes.map((note) => (
          <article key={note.symbol} className="card-row p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <span className="font-bold text-(--text-primary)">{note.symbol}</span>
                <span className="ml-2 text-xs text-(--text-secondary)">{note.name}</span>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${tone[note.stance]}`}>
                {note.stance}
              </span>
            </div>
            <p className="mt-2 text-sm text-(--text-primary)">{note.summary}</p>
            {note.live_price != null && (
              <p className="mt-1 num-tabular text-xs text-(--text-secondary)">
                Live ₹{note.live_price.toLocaleString("en-IN")}
                {note.pe_ratio != null ? ` · P/E ${note.pe_ratio}` : " · P/E unavailable"}
                {note.one_year_price_change_pct != null
                  ? ` · 1Y ${note.one_year_price_change_pct}%`
                  : ""}
              </p>
            )}
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-(--text-secondary)">
              {note.reasons.map((item) => (
                <li key={item}>{item}</li>
              ))}
              {note.blockers.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
