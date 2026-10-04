"use client";

import { TrendingUp, TrendingDown, Minus, DollarSign, Percent } from "lucide-react";
import { IndexQuote, MacroSnapshot } from "@/lib/types";

interface MarketMoodStripProps {
  indices: IndexQuote[];
  macro: MacroSnapshot | null;
  loading?: boolean;
}

function formatDataDate(iso: string | undefined) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

export function MarketMoodStrip({ indices, macro, loading }: MarketMoodStripProps) {
  const nifty = indices.find((item) => item.name.toUpperCase().includes("NIFTY"));
  // "Mood" here is nothing more than NIFTY's own day-change sign, restated as a chip —
  // not a separate fabricated indicator. Flat/unavailable shows a neutral dash rather
  // than guessing a direction.
  const moodUp = nifty ? nifty.day_change_percentage > 0 : null;
  const moodDown = nifty ? nifty.day_change_percentage < 0 : null;

  if (loading) {
    return (
      <div className="mt-4 flex gap-2.5 overflow-x-auto">
        <div className="skeleton h-14 w-40 shrink-0 rounded-xl" />
        <div className="skeleton h-14 w-40 shrink-0 rounded-xl" />
        <div className="skeleton h-14 w-40 shrink-0 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="mt-4 flex gap-2.5 overflow-x-auto pb-1">
      <div className="card-row flex shrink-0 items-center gap-2.5 px-4 py-3">
        {moodUp && <TrendingUp className="h-4 w-4 text-(--bull-green)" />}
        {moodDown && <TrendingDown className="h-4 w-4 text-(--bear-red)" />}
        {moodUp === null && <Minus className="h-4 w-4 text-(--text-muted)" />}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-(--text-muted)">Market mood</div>
          <div
            className={`text-sm font-bold ${
              moodUp ? "text-(--bull-green)" : moodDown ? "text-(--bear-red)" : "text-(--text-primary)"
            }`}
          >
            {nifty ? (moodUp ? "Risk-on" : moodDown ? "Risk-off" : "Flat") : "—"}
          </div>
        </div>
      </div>

      <div className="card-row flex shrink-0 items-center gap-2.5 px-4 py-3">
        <DollarSign className="h-4 w-4 text-(--section-portfolio)" />
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-(--text-muted)">USD/INR</div>
          {macro?.usd_inr.status === "OK" ? (
            <div className="num-tabular text-sm font-bold text-(--text-primary)">
              ₹{macro.usd_inr.value?.toFixed(2)}
            </div>
          ) : (
            <div className="text-sm font-semibold text-(--text-muted)">Data unavailable</div>
          )}
        </div>
      </div>

      <div className="card-row flex shrink-0 items-center gap-2.5 px-4 py-3">
        <Percent className="h-4 w-4 text-(--section-gold)" />
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-(--text-muted)">
            CPI inflation (YoY)
          </div>
          {macro?.cpi_inflation_yoy.status === "OK" ? (
            <div className="num-tabular text-sm font-bold text-(--text-primary)">
              {macro.cpi_inflation_yoy.value_pct?.toFixed(2)}%
              <span className="ml-1 text-[10px] font-normal text-(--text-muted)">
                as of {formatDataDate(macro.cpi_inflation_yoy.data_date)}
              </span>
            </div>
          ) : (
            <div className="text-sm font-semibold text-(--text-muted)">Data unavailable</div>
          )}
        </div>
      </div>
    </div>
  );
}
