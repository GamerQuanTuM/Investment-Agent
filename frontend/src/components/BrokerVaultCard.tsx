"use client";

import React from "react";
import { BrokerVaultState } from "../lib/types";
import { Wallet, ShieldAlert, CheckCircle2 } from "lucide-react";

interface BrokerVaultCardProps {
  broker: BrokerVaultState | null;
  error: string | null;
  loading: boolean;
}

export const BrokerVaultCard: React.FC<BrokerVaultCardProps> = ({ broker, error, loading }) => {
  const holdings = broker?.holdings ?? [];

  return (
    <div className="card flex flex-col gap-0 overflow-hidden">
      {/* Header with Broker Auth details */}
      <div className="flex items-center justify-between border-b border-(--border-subtle) p-5 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="icon-badge w-9 h-9 bg-(--section-portfolio-soft) text-(--section-portfolio)">
            <Wallet className="w-4.5 h-4.5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-(--text-primary)">Demat Holdings</h2>
            <p className="text-[11px] text-(--text-secondary)">
              {broker?.auth_status === "CONNECTED" ? "Live from INDmoney · NSE" : "Broker not connected"}
            </p>
          </div>
        </div>
        <div
          className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-semibold ${
            broker?.auth_status === "CONNECTED"
              ? "bg-(--bull-green-soft) text-(--bull-green)"
              : "bg-(--surface-3) text-(--text-muted)"
          }`}
        >
          <CheckCircle2 className="w-3 h-3" />
          <span>{broker?.auth_status === "CONNECTED" ? "Connected" : "Not connected"}</span>
        </div>
      </div>

      {/* Risk caps strip */}
      <div className="flex items-center gap-4 overflow-x-auto border-b border-(--border-subtle) bg-(--section-research-soft) px-5 py-2.5 text-[11px]">
        <span className="flex items-center gap-1.5 font-bold text-(--text-primary)">
          <ShieldAlert className="w-3.5 h-3.5 text-(--section-research)" />
          Safeguard caps
        </span>
        <span className="whitespace-nowrap text-(--text-secondary)">Single stock <b className="text-(--text-primary)">max 15%</b></span>
        <span className="whitespace-nowrap text-(--text-secondary)">Sector <b className="text-(--text-primary)">max 25%</b></span>
        <span className="whitespace-nowrap text-(--text-secondary)">Horizon <b className="text-(--text-primary)">3–5y</b></span>
      </div>

      {/* Holdings table */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-140 text-sm">
          <thead>
            <tr className="border-b border-(--border-subtle) text-left text-[11px] font-semibold uppercase tracking-wide text-(--text-muted)">
              <th className="px-5 py-2.5">Stock</th>
              <th className="px-3 py-2.5 text-right">Qty · Avg</th>
              <th className="px-3 py-2.5 text-right">LTP</th>
              <th className="px-3 py-2.5 text-right">Current value</th>
              <th className="px-3 py-2.5 text-right">P&amp;L</th>
              <th className="px-5 py-2.5 text-right">Allocation</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i}>
                  <td colSpan={6} className="px-5 py-2">
                    <div className="skeleton h-10 w-full" />
                  </td>
                </tr>
              ))}
            {error && (
              <tr>
                <td colSpan={6} className="px-5 py-4 text-xs text-(--bear-red)">{error}</td>
              </tr>
            )}
            {!loading && !error && holdings.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-4 text-xs text-(--text-muted)">No Demat holdings returned.</td>
              </tr>
            )}
            {holdings.map((h) => {
              const isProfit = (h.unrealized_pnl ?? 0) >= 0;
              return (
                <tr key={h.symbol} className="border-b border-(--border-subtle) transition-colors hover:bg-(--surface-2)">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="icon-badge h-8 w-8 shrink-0 bg-(--section-portfolio-soft) text-[11px] font-bold text-(--section-portfolio)">
                        {h.symbol.slice(0, 2)}
                      </span>
                      <div>
                        <div className="font-bold text-(--text-primary)">{h.symbol}</div>
                        <div className="text-[11px] text-(--text-secondary)">{h.sector}</div>
                      </div>
                    </div>
                  </td>
                  <td className="num-tabular px-3 py-3 text-right text-xs text-(--text-secondary)">
                    {h.quantity} · ₹{h.avg_buy_price.toLocaleString("en-IN")}
                  </td>
                  <td className="num-tabular px-3 py-3 text-right font-semibold text-(--text-primary)">
                    {h.current_ltp != null ? `₹${h.current_ltp.toLocaleString("en-IN")}` : "—"}
                  </td>
                  <td className="num-tabular px-3 py-3 text-right font-bold text-(--text-primary)">
                    ₹{h.current_value.toLocaleString("en-IN")}
                  </td>
                  <td className={`num-tabular px-3 py-3 text-right text-xs font-semibold ${isProfit ? "text-(--bull-green)" : "text-(--bear-red)"}`}>
                    {h.unrealized_pnl == null
                      ? "—"
                      : `${isProfit ? "+" : ""}₹${h.unrealized_pnl.toLocaleString("en-IN")} (${isProfit ? "+" : ""}${h.unrealized_pnl_pct}%)`}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-(--surface-3)">
                        <div
                          className="h-full rounded-full bg-(--section-portfolio)"
                          style={{ width: `${Math.min(h.allocation_pct, 100)}%` }}
                        />
                      </div>
                      <span className="num-tabular w-10 text-right text-[11px] font-medium text-(--text-muted)">
                        {h.allocation_pct}%
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
