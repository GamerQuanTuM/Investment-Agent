"use client";

import React from "react";
import { ResearchCandidate } from "../lib/types";
import { Play, Sparkles, Building2, CheckCircle2, AlertOctagon } from "lucide-react";

interface ResearchRunnerProps {
  candidates: ResearchCandidate[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  monthlyBudget: number;
  onChangeMonthlyBudget: (budget: number) => void;
  isRunning: boolean;
  onRunResearch: () => void;
}

export const ResearchRunner: React.FC<ResearchRunnerProps> = ({
  candidates,
  selectedSymbol,
  onSelectSymbol,
  monthlyBudget,
  onChangeMonthlyBudget,
  isRunning,
  onRunResearch,
}) => {
  const currentCandidate =
    candidates.find((c) => c.symbol === selectedSymbol) || candidates[0];

  const budgetOptions = [10000, 25000, 50000, 100000];

  return (
    <div className="card p-5 flex flex-col gap-5">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-(--border-subtle) pb-3.5">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-9 w-9 bg-(--section-research-soft) text-(--section-research)">
            <Sparkles className="w-4.5 h-4.5" />
          </span>
          <div>
            <h2 className="text-sm font-bold text-(--text-primary)">
              Deterministic Screening &amp; Research Graph
            </h2>
            <p className="text-xs text-(--text-secondary) mt-0.5">
              Pre-filters candidate balance sheets before triggering LLM thesis synthesis
            </p>
          </div>
        </div>

        {/* Action Button */}
        <button
          onClick={onRunResearch}
          disabled={isRunning}
          className="flex items-center justify-center gap-2 rounded-xl bg-(--section-research) px-4 py-2 font-semibold text-xs tracking-tight text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className={`w-3.5 h-3.5 fill-current ${isRunning ? "animate-spin" : ""}`} />
          <span>{isRunning ? "Executing LangGraph…" : "Run Research Pipeline"}</span>
        </button>
      </div>

      {/* Candidate Selector Grid */}
      <div>
        <label className="text-xs font-semibold uppercase tracking-wider text-(--text-secondary) block mb-2">
          Select Candidate Asset (NSE / BSE)
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
          {candidates.map((c) => {
            const isSelected = c.symbol === selectedSymbol;
            return (
              <button
                key={c.symbol}
                onClick={() => onSelectSymbol(c.symbol)}
                className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                  isSelected
                    ? "bg-(--section-research-soft) border-(--section-research)/40 text-(--section-research)"
                    : "card-row card-interactive text-(--text-secondary)"
                }`}
              >
                <div className="font-bold text-sm text-(--text-primary)">{c.symbol}</div>
                <div className="text-[10px] text-(--text-secondary) truncate mt-0.5">
                  {c.company_name.split(" ")[0]}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Candidate Fundamental Scorecard */}
      {currentCandidate && (
        <div className="card-row p-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-3">
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-(--text-secondary)" />
              <span className="font-semibold text-sm text-(--text-primary)">
                {currentCandidate.company_name}
              </span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-(--section-portfolio-soft) text-(--section-portfolio) font-medium">
                {currentCandidate.sector}
              </span>
            </div>
            <span className="text-xs text-(--text-secondary) num-tabular">
              Market Cap: ₹{currentCandidate.market_cap_cr.toLocaleString("en-IN")} Cr
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
            <div className="p-2.5 rounded-lg bg-(--surface-1) border border-(--border-subtle)">
              <span className="text-(--text-secondary) block text-[11px]">Debt to Equity</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="font-semibold num-tabular text-(--text-primary)">
                  {currentCandidate.debt_to_equity}x
                </span>
                {currentCandidate.debt_to_equity <= 0.5 ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-(--bull-green)" />
                ) : (
                  <AlertOctagon className="w-3.5 h-3.5 text-(--bear-red)" />
                )}
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-(--surface-1) border border-(--border-subtle)">
              <span className="text-(--text-secondary) block text-[11px]">Promoter Pledge</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="font-semibold num-tabular text-(--text-primary)">
                  {currentCandidate.promoter_pledge_pct}%
                </span>
                {currentCandidate.promoter_pledge_pct === 0 ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-(--bull-green)" />
                ) : (
                  <AlertOctagon className="w-3.5 h-3.5 text-(--bear-red)" />
                )}
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-(--surface-1) border border-(--border-subtle)">
              <span className="text-(--text-secondary) block text-[11px]">3Y ROCE Avg</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="font-semibold num-tabular text-(--bull-green)">
                  {currentCandidate.roce_pct}%
                </span>
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-(--surface-1) border border-(--border-subtle)">
              <span className="text-(--text-secondary) block text-[11px]">Valuation (P/E)</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="font-semibold num-tabular text-(--text-primary)">
                  {currentCandidate.pe_ratio}x
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Monthly Budget Controller */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-(--section-research-soft) border border-(--border-subtle)">
        <div>
          <span className="text-xs font-semibold text-(--text-primary) block">
            Target Monthly Investment Budget
          </span>
          <span className="text-[11px] text-(--text-secondary)">
            Enforces strict capital allocation and rebalancing constraints
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {budgetOptions.map((opt) => (
            <button
              key={opt}
              onClick={() => onChangeMonthlyBudget(opt)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium num-tabular transition-colors cursor-pointer ${
                monthlyBudget === opt
                  ? "bg-(--section-research) text-white font-semibold"
                  : "bg-(--surface-1) text-(--text-secondary) hover:bg-(--surface-2) border border-(--border-subtle)"
              }`}
            >
              ₹{(opt / 1000).toLocaleString("en-IN")}k
            </button>
          ))}
          <div className="px-3 py-1.5 rounded-lg bg-(--surface-1) border border-(--border-subtle) text-xs font-bold text-(--text-primary) num-tabular">
            ₹{monthlyBudget.toLocaleString("en-IN")}
          </div>
        </div>
      </div>
    </div>
  );
};
