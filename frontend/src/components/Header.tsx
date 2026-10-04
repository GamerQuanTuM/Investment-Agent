"use client";

import React from "react";
import { HealthStatus, BrokerVaultState, IndexQuote } from "../lib/types";
import { Cpu, RefreshCw, Radio, TrendingUp, TrendingDown } from "lucide-react";

interface HeaderProps {
  health: HealthStatus | null;
  broker: BrokerVaultState | null;
  indices: IndexQuote[];
  isRefreshing: boolean;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  broker,
  indices,
  isRefreshing,
  onRefresh,
}) => {
  return (
    <div className="border-b border-(--border-subtle) bg-(--surface-1)">
      <div className="mx-auto flex max-w-7xl items-center gap-4 overflow-x-auto px-4 py-2 lg:px-8">
        {/* Index ticker */}
        <div className="flex items-center gap-4 text-xs">
          {indices.length === 0 && <span className="text-(--text-muted)">Indices unavailable</span>}
          {indices.map((index) => {
            const up = index.day_change_percentage >= 0;
            return (
              <div key={index.name} className="flex items-center gap-1.5 whitespace-nowrap">
                {up ? (
                  <TrendingUp className="h-3 w-3 text-(--bull-green)" />
                ) : (
                  <TrendingDown className="h-3 w-3 text-(--bear-red)" />
                )}
                <span className="font-semibold text-(--text-primary)">{index.name}</span>
                <span className="num-tabular text-(--text-secondary)">
                  {index.live_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                </span>
                <span className={`num-tabular font-semibold ${up ? "text-(--bull-green)" : "text-(--bear-red)"}`}>
                  {up ? "+" : ""}
                  {index.day_change_percentage.toFixed(2)}%
                </span>
              </div>
            );
          })}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2 text-xs">
          <div className="hidden items-center gap-1.5 whitespace-nowrap text-(--text-secondary) md:flex">
            <Radio className="h-3 w-3 text-(--section-portfolio) animate-pulse" />
            {broker?.auth_status === "CONNECTED" ? "INDmoney connected" : "Broker unavailable"}
          </div>
          <div className="hidden items-center gap-1.5 whitespace-nowrap text-(--text-secondary) lg:flex">
            <Cpu className="h-3 w-3 text-(--section-chat)" />
            {health?.routing_tiers?.primary || "routing unavailable"}
          </div>
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 rounded-full border border-(--border-subtle) bg-(--surface-2) px-3 py-1 text-(--text-secondary) transition-colors hover:bg-(--surface-3) disabled:opacity-50"
            title="Refresh live broker quotes and agent state"
          >
            <RefreshCw className={`h-3 w-3 ${isRefreshing ? "animate-spin" : ""}`} />
            Sync
          </button>
        </div>
      </div>
    </div>
  );
};
