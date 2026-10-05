import { AlertTriangle } from "lucide-react";
import { StockPlan } from "@/lib/types";

const DONUT_COLORS = [
  "var(--section-portfolio)",
  "var(--section-stocks)",
  "var(--section-sip)",
  "var(--section-research)",
  "var(--section-gold)",
  "var(--section-chat)",
  "var(--bear-red)",
  "var(--text-muted)",
];

const inr = (value: number) => `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

function Unavailable() {
  return <span className="rounded bg-(--surface-3) px-1.5 py-0.5 text-[10px] text-(--text-muted)">Data unavailable</span>;
}

function SectorDonut({ split }: { split: StockPlan["sector_split"] }) {
  const radius = 15.9155; // circumference is 100, so a stroke length equals its percentage
  // Each slice starts where the previous one ended (running total of the percentages before it).
  const offsets = split.map((_, index) => split.slice(0, index).reduce((sum, slice) => sum + slice.pct, 0));
  return (
    <div className="flex items-center gap-4">
      <svg
        viewBox="0 0 42 42"
        className="h-24 w-24 shrink-0 -rotate-90"
        role="img"
        aria-label="Sector split of the money invested"
      >
        <circle cx="21" cy="21" r={radius} fill="none" stroke="var(--surface-3)" strokeWidth="6" />
        {split.map((slice, index) => (
          <circle
            key={slice.sector}
            cx="21"
            cy="21"
            r={radius}
            fill="none"
            stroke={DONUT_COLORS[index % DONUT_COLORS.length]}
            strokeWidth="6"
            strokeDasharray={`${slice.pct} ${100 - slice.pct}`}
            strokeDashoffset={-offsets[index]}
          />
        ))}
      </svg>
      <ul className="space-y-1 text-[11px]">
        {split.map((slice, index) => (
          <li key={slice.sector} className="flex items-center gap-1.5 text-(--text-secondary)">
            <span className="h-2 w-2 rounded-full" style={{ background: DONUT_COLORS[index % DONUT_COLORS.length] }} />
            <span>{slice.sector}</span>
            <span className="num-tabular font-semibold text-(--text-primary)">{slice.pct}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StockPlanCard({ plan }: { plan: StockPlan }) {
  return (
    <div className="space-y-3 rounded-xl border border-(--border-subtle) bg-(--surface-1) p-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[460px] text-left text-xs">
          <thead>
            <tr className="border-b border-(--border-subtle) text-[10px] uppercase tracking-wide text-(--text-muted)">
              <th className="py-1.5 pr-2 font-semibold">Stock</th>
              <th className="py-1.5 pr-2 font-semibold">Sector</th>
              <th className="py-1.5 pr-2 text-right font-semibold">Price</th>
              <th className="py-1.5 pr-2 text-right font-semibold">Shares</th>
              <th className="py-1.5 pr-2 text-right font-semibold">Amount</th>
              <th className="py-1.5 text-right font-semibold">%</th>
            </tr>
          </thead>
          <tbody>
            {plan.rows.map((row) => (
              <tr key={row.symbol} className="border-b border-(--border-subtle) last:border-0" title={row.why.join(" · ")}>
                <td className="py-1.5 pr-2">
                  <div className="font-bold text-(--text-primary)">{row.symbol}</div>
                  <div className="max-w-[10rem] truncate text-[10px] text-(--text-muted)">{row.name}</div>
                </td>
                <td className="py-1.5 pr-2 text-(--text-secondary)">{row.sector}</td>
                <td className="num-tabular py-1.5 pr-2 text-right">{row.price != null ? inr(row.price) : <Unavailable />}</td>
                <td className="num-tabular py-1.5 pr-2 text-right">{row.shares}</td>
                <td className="num-tabular py-1.5 pr-2 text-right font-semibold text-(--text-primary)">{inr(row.amount_inr)}</td>
                <td className="num-tabular py-1.5 text-right">{row.weight_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-0.5 text-[11px] text-(--text-secondary)">
        {plan.rows.map((row) => (
          <li key={row.symbol}>
            <span className="font-semibold text-(--text-primary)">{row.symbol}</span>: {row.why.join(" · ")}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-(--border-subtle) pt-2 text-xs">
        <span className="text-(--text-secondary)">
          Invested <span className="num-tabular font-bold text-(--text-primary)">{inr(plan.total_invested)}</span> of {inr(plan.budget)}
        </span>
        <span className="text-(--text-secondary)">
          Leftover cash <span className="num-tabular font-bold text-(--text-primary)">{inr(plan.leftover)}</span>
        </span>
        <span className="text-(--text-muted)">{plan.data_as_of ? `Prices as of ${plan.data_as_of}` : <Unavailable />}</span>
      </div>

      <SectorDonut split={plan.sector_split} />

      {plan.reality_check && (
        <div
          role="note"
          className="flex gap-2 rounded-lg border border-(--section-gold)/40 bg-(--section-gold-soft) p-2.5 text-xs leading-relaxed text-(--text-primary)"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
          <div>
            <div className="font-bold text-(--section-gold)">Reality check</div>
            {plan.reality_check.replace(/^Reality check:\s*/, "")}
          </div>
        </div>
      )}

      <p className="text-[10px] leading-relaxed text-(--text-muted)">
        {plan.growth_note} {plan.disclaimer}
      </p>
    </div>
  );
}

export function DataUnavailableTile({ message }: { message: string }) {
  return (
    <div role="note" className="rounded-xl border border-dashed border-(--border-medium) bg-(--surface-2) p-3 text-xs text-(--text-secondary)">
      <div className="mb-1 inline-flex items-center gap-1.5 font-bold text-(--text-primary)">
        <AlertTriangle className="h-3.5 w-3.5 text-(--section-gold)" /> Data unavailable
      </div>
      <p className="leading-relaxed">{message}</p>
    </div>
  );
}
