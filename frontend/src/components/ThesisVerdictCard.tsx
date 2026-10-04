"use client";

import React from "react";
import { ResearchRunResult } from "../lib/types";
import { CheckCircle, XCircle, Target } from "lucide-react";

interface ThesisVerdictCardProps {
  result: ResearchRunResult;
}

export const ThesisVerdictCard: React.FC<ThesisVerdictCardProps> = ({ result }) => {
  const rec = result.recommendation;
  const isOpportunity = rec.decision === "OPPORTUNITY";

  const badge = isOpportunity
    ? {
        bg: "bg-(--bull-green-soft) text-(--bull-green)",
        icon: <CheckCircle className="w-5 h-5" />,
        label: "OPPORTUNITY",
      }
    : {
        bg: "bg-(--surface-3) text-(--text-muted)",
        icon: <XCircle className="w-5 h-5" />,
        label: "NO ACTION",
      };

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-(--border-subtle) pb-4">
        <div className="flex items-center gap-3">
          <div className={`icon-badge p-2.5 ${badge.bg}`}>{badge.icon}</div>
          <div>
            <div className="text-[11px] font-medium text-(--text-secondary)">Agent Final Recommendation</div>
            <h3 className="text-base font-bold text-(--text-primary) tracking-tight">
              {rec.asset_id || rec.name || "No candidate"} — {badge.label}
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="card-row px-3 py-1.5">
            <span className="text-(--text-secondary) text-[11px] block">Confidence</span>
            <span className="font-bold text-(--text-primary) num-tabular">{Math.round((result.confidence ?? 0) * 100)}%</span>
          </div>
          <div className="card-row px-3 py-1.5">
            <span className="text-(--text-secondary) text-[11px] block">Evidence Quality</span>
            <span className="font-bold text-(--bull-green)">{result.evidence_quality || "UNKNOWN"}</span>
          </div>
        </div>
      </div>

      {isOpportunity ? (
        <div className="card-row p-3.5 flex flex-col justify-between">
          <span className="text-xs font-semibold text-(--text-secondary) flex items-center gap-1.5 mb-1.5">
            <Target className="w-3.5 h-3.5 text-(--section-portfolio)" />
            <span>Proposed Monthly Allocation</span>
          </span>
          <div className="text-base font-bold text-(--text-primary) num-tabular">
            ₹{(rec.proposed_monthly_allocation ?? 0).toLocaleString("en-IN")}
            <span className="text-xs font-normal text-(--text-secondary) ml-1.5">/month · {rec.horizon_years ?? "—"} year horizon</span>
          </div>
          {rec.action_items && rec.action_items.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-(--text-secondary)">
              {rec.action_items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="card-row p-3.5">
          <span className="text-xs font-semibold text-(--text-secondary) block mb-1">Why no action</span>
          <p className="text-sm text-(--text-primary) leading-relaxed">
            {rec.reason || "No candidate passed the deterministic screen or evidence verification this run."}
          </p>
        </div>
      )}
    </div>
  );
};
