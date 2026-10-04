"use client";

import React, { useState } from "react";
import { ResearchReport } from "../lib/types";
import { ShieldCheck, FileSpreadsheet, Lightbulb, Compass, AlertTriangle, HelpCircle, ExternalLink } from "lucide-react";

interface EvidenceInspectorProps {
  report: ResearchReport;
  symbol: string;
}

export const EvidenceInspector: React.FC<EvidenceInspectorProps> = ({ report, symbol }) => {
  const [activeTab, setActiveTab] = useState<"facts" | "interpretations" | "assumptions" | "uncertainties" | "risks">("facts");

  const tabs = [
    {
      id: "facts" as const,
      label: "Facts",
      items: report.FACT || [],
      icon: <FileSpreadsheet className="w-3.5 h-3.5 text-(--bull-green)" />,
      description: "Hard balance sheet data, verified filings & zero-hallucination calculations.",
    },
    {
      id: "interpretations" as const,
      label: "Interpretations",
      items: report.INTERPRETATION || [],
      icon: <Lightbulb className="w-3.5 h-3.5 text-(--section-portfolio)" />,
      description: "Analytical derivations of operating leverage and historical multiples.",
    },
    {
      id: "assumptions" as const,
      label: "Assumptions",
      items: report.ASSUMPTION || [],
      icon: <Compass className="w-3.5 h-3.5 text-(--section-gold)" />,
      description: "Explicit forward-looking premises required for this investment thesis.",
    },
    {
      id: "uncertainties" as const,
      label: "Uncertainties",
      items: report.UNCERTAINTY || [],
      icon: <HelpCircle className="w-3.5 h-3.5 text-(--section-chat)" />,
      description: "Open questions the screen could not resolve from sourced data.",
    },
    {
      id: "risks" as const,
      label: "Risks",
      items: report.RISK || [],
      icon: <AlertTriangle className="w-3.5 h-3.5 text-(--bear-red)" />,
      description: "Conditions that would break this thesis.",
    },
  ];

  const currentTab = tabs.find((t) => t.id === activeTab) || tabs[0];

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-(--border-subtle) pb-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-8 w-8 bg-(--section-research-soft) text-(--section-research)">
            <ShieldCheck className="w-4 h-4" />
          </span>
          <h2 className="text-sm font-bold text-(--text-primary)">Evidence Partitioning Matrix ({symbol})</h2>
        </div>
        <span className="text-[11px] text-(--text-secondary) font-medium">Truth-in-Evidence Protocol</span>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-(--border-subtle) pb-3">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`nav-pill flex items-center gap-2 px-3 py-2 text-xs font-medium transition-all cursor-pointer ${
                isActive
                  ? "bg-(--surface-3) text-(--text-primary) border border-(--border-medium)"
                  : "bg-(--surface-2) text-(--text-secondary) hover:text-(--text-primary) border border-transparent"
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-(--surface-3) text-(--text-secondary) num-tabular">
                {tab.items.length}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-(--text-secondary) italic">{currentTab.description}</p>

      <div className="space-y-2">
        {currentTab.items.map((item, idx) => (
          <div key={idx} className="card-row flex items-start gap-3 p-3">
            <span className="text-[11px] font-bold text-(--text-muted) num-tabular mt-0.5">0{idx + 1}</span>
            <p className="text-xs text-(--text-primary) leading-relaxed">{item}</p>
          </div>
        ))}
        {currentTab.items.length === 0 && <p className="text-xs text-(--text-muted)">Nothing recorded for this category.</p>}
      </div>

      {report.EVIDENCE_SOURCES && report.EVIDENCE_SOURCES.length > 0 && (
        <div className="border-t border-(--border-subtle) pt-3">
          <span className="text-[11px] font-bold uppercase tracking-wide text-(--text-muted)">Sources</span>
          <ul className="mt-1.5 space-y-1">
            {report.EVIDENCE_SOURCES.map((source, idx) => (
              <li key={idx}>
                {source.source_url ? (
                  <a
                    href={source.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-xs font-medium text-(--section-portfolio) hover:underline"
                  >
                    <ExternalLink className="h-3 w-3" /> {source.source_name || source.source_url}
                  </a>
                ) : (
                  <span className="text-xs text-(--text-muted)">{source.source_name || "Unnamed source"}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
