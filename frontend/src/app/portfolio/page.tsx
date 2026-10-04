"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Wallet, PieChart, ShieldAlert, AlertTriangle, Info, Layers } from "lucide-react";
import { fetchBrokerVault, fetchPortfolioAlerts, fetchPortfolioConcentration } from "@/lib/api";
import { ScoreRing } from "@/components/ScoreRing";

const SECTOR_COLORS = [
  "var(--section-portfolio)",
  "var(--section-stocks)",
  "var(--section-sip)",
  "var(--section-research)",
  "var(--section-gold)",
  "var(--section-chat)",
  "var(--text-muted)",
];

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

export default function PortfolioPage() {
  const broker = useQuery({ queryKey: ["portfolio"], queryFn: fetchBrokerVault, retry: false });
  const concentration = useQuery({
    queryKey: ["portfolio-concentration"],
    queryFn: fetchPortfolioConcentration,
    retry: false,
  });
  const alerts = useQuery({ queryKey: ["portfolio-alerts"], queryFn: fetchPortfolioAlerts, retry: false });

  const holdings = broker.data?.holdings ?? [];
  const notConnected = broker.data?.auth_status === "DISCONNECTED";
  const sectorEntries = Object.entries(concentration.data?.sector_exposure_pct ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <div className="flex items-center gap-2.5">
        <span className="icon-badge h-9 w-9 bg-(--section-portfolio-soft) text-(--section-portfolio)">
          <Wallet className="h-4.5 w-4.5" />
        </span>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-(--text-primary)">Portfolio</h1>
          <p className="text-sm text-(--text-secondary)">
            Concentration and alerts, computed from your live Demat holdings — read-only, no trade actions here.
          </p>
        </div>
      </div>

      {notConnected && (
        <div className="card mt-5 flex items-center gap-3 p-4">
          <span className="icon-badge h-9 w-9 bg-(--surface-3) text-(--text-muted)">
            <Info className="h-4.5 w-4.5" />
          </span>
          <p className="text-sm text-(--text-secondary)">
            No broker connected — configure INDstocks credentials on the backend to see concentration and alerts for
            real holdings.
          </p>
        </div>
      )}

      {/* Alerts */}
      <div aria-live="polite" className="mt-5 space-y-2">
        {(alerts.data?.alerts ?? []).map((alert, index) => (
          <div
            key={`${alert.kind}-${index}`}
            className={`card-row flex items-start gap-2.5 px-4 py-3 text-sm ${
              alert.severity === "WARNING" ? "text-(--bear-red)" : "text-(--text-primary)"
            }`}
          >
            {alert.severity === "WARNING" ? (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-(--section-gold)" />
            )}
            {alert.message}
          </div>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Concentration */}
        <section className="card p-5 lg:col-span-7">
          <div className="flex items-center gap-2.5">
            <span className="icon-badge h-9 w-9 bg-(--section-research-soft) text-(--section-research)">
              <PieChart className="h-4.5 w-4.5" />
            </span>
            <h2 className="text-sm font-bold text-(--text-primary)">Sector exposure</h2>
          </div>
          {sectorEntries.length > 0 ? (
            <>
              <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full">
                {sectorEntries.map(([sector, pct], index) => (
                  <div
                    key={sector}
                    style={{ width: `${pct}%`, backgroundColor: SECTOR_COLORS[index % SECTOR_COLORS.length] }}
                  />
                ))}
              </div>
              <div className="mt-3 space-y-1.5">
                {sectorEntries.map(([sector, pct], index) => (
                  <div key={sector} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-(--text-secondary)">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: SECTOR_COLORS[index % SECTOR_COLORS.length] }}
                      />
                      {sector}
                    </span>
                    <span className="num-tabular font-semibold text-(--text-primary)">{pct}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-(--text-secondary)">No holdings to analyze yet.</p>
          )}
        </section>

        <section className="card flex flex-col items-center justify-center gap-3 p-5 lg:col-span-5">
          <ScoreRing label="Diversification" score={concentration.data?.diversification_score ?? null} size={110} />
          <p className="text-center text-xs text-(--text-secondary)">
            100 minus your single biggest sector&apos;s share — spread wide scores high, one sector dominating
            pulls it down.
          </p>
        </section>
      </div>

      {/* Holdings */}
      <section className="card mt-5 overflow-hidden">
        <div className="flex items-center gap-2.5 border-b border-(--border-subtle) p-5 pb-4">
          <span className="icon-badge h-9 w-9 bg-(--section-stocks-soft) text-(--section-stocks)">
            <Layers className="h-4.5 w-4.5" />
          </span>
          <h2 className="text-sm font-bold text-(--text-primary)">Holdings</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-140 text-sm">
            <thead>
              <tr className="border-b border-(--border-subtle) text-left text-[11px] font-semibold uppercase tracking-wide text-(--text-muted)">
                <th className="px-5 py-2.5">Stock</th>
                <th className="px-3 py-2.5 text-right">Allocation</th>
                <th className="px-3 py-2.5 text-right">Value</th>
                <th className="px-5 py-2.5 text-right">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.symbol} className="border-b border-(--border-subtle) last:border-0">
                  <td className="px-5 py-3">
                    <Link href={`/stocks/${h.symbol}`} className="font-semibold text-(--text-primary) hover:underline">
                      {h.symbol}
                    </Link>
                  </td>
                  <td className="num-tabular px-3 py-3 text-right text-(--text-secondary)">{h.allocation_pct}%</td>
                  <td className="num-tabular px-3 py-3 text-right text-(--text-primary)">{money(h.current_value)}</td>
                  <td
                    className={`num-tabular px-5 py-3 text-right font-semibold ${
                      (h.unrealized_pnl ?? 0) >= 0 ? "text-(--bull-green)" : "text-(--bear-red)"
                    }`}
                  >
                    {h.unrealized_pnl != null ? `${money(h.unrealized_pnl)} (${h.unrealized_pnl_pct}%)` : "—"}
                  </td>
                </tr>
              ))}
              {holdings.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-6 text-center text-sm text-(--text-secondary)">
                    <ShieldAlert className="mx-auto mb-1.5 h-4 w-4 text-(--text-muted)" />
                    No holdings yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
