"use client";

import React from "react";
import { BullCase, BearCase } from "../lib/types";
import { TrendingUp, AlertCircle, ArrowLeftRight } from "lucide-react";

interface DialecticArenaProps {
  bullCase: BullCase | null | undefined;
  bearCase: BearCase | null | undefined;
  symbol: string;
}

export const DialecticArena: React.FC<DialecticArenaProps> = ({ bullCase, bearCase, symbol }) => {
  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-(--border-subtle) pb-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-8 w-8 bg-(--section-research-soft) text-(--section-research)">
            <ArrowLeftRight className="w-4 h-4" />
          </span>
          <h2 className="text-sm font-bold text-(--text-primary)">Dialectic Tension: Bull Thesis vs. Bear Interrogation</h2>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        <div className="p-4 rounded-xl bg-(--bull-green-soft) border border-(--bull-green)/20 flex flex-col">
          <div className="flex items-center gap-2 text-(--bull-green) text-xs font-bold mb-2">
            <TrendingUp className="w-4 h-4" />
            <span>The Bull Case for {symbol}</span>
          </div>
          {bullCase && bullCase.thesis.length > 0 ? (
            <ul className="list-disc space-y-1.5 pl-4 text-xs text-(--text-primary) leading-relaxed flex-1">
              {bullCase.thesis.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-(--text-secondary)">No bull case recorded for this run.</p>
          )}
          {bullCase && bullCase.assumptions.length > 0 && (
            <div className="mt-3 pt-2.5 border-t border-(--bull-green)/20 text-[10px] text-(--bull-green) font-semibold">
              Assumption: {bullCase.assumptions[0]}
            </div>
          )}
        </div>

        <div className="p-4 rounded-xl bg-(--bear-red-soft) border border-(--bear-red)/20 flex flex-col">
          <div className="flex items-center gap-2 text-(--bear-red) text-xs font-bold mb-2">
            <AlertCircle className="w-4 h-4" />
            <span>The Bear Interrogation</span>
          </div>
          {bearCase && bearCase.thesis_break_conditions.length > 0 ? (
            <ul className="list-disc space-y-1.5 pl-4 text-xs text-(--text-primary) leading-relaxed flex-1">
              {bearCase.thesis_break_conditions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-(--text-secondary)">No bear case recorded for this run.</p>
          )}
          {bearCase && bearCase.counterarguments.length > 0 && (
            <div className="mt-3 pt-2.5 border-t border-(--bear-red)/20 text-[10px] text-(--bear-red) font-semibold">
              {bearCase.counterarguments[0]}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
