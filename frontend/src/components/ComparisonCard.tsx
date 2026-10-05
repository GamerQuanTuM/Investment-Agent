"use client";

import { Scale } from "lucide-react";
import { ChatComparison } from "@/lib/types";

/**
 * Side-by-side comparison of two (or three) finance terms. On a phone each row stacks its
 * columns under the row label; from `sm` up it becomes a real table with one column per term.
 */
export function ComparisonCard({ comparison }: { comparison: ChatComparison }) {
  const { columns, rows, takeaway, title } = comparison;
  const cells = (row: ChatComparison["rows"][number]) => [row.a, row.b, row.c].slice(0, columns.length);
  const grid = columns.length === 3 ? "sm:grid-cols-[8rem_repeat(3,minmax(0,1fr))]" : "sm:grid-cols-[8rem_repeat(2,minmax(0,1fr))]";

  return (
    <div className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-1) p-3 text-left whitespace-normal">
      <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-(--section-chat)">
        <Scale className="h-3.5 w-3.5" />
        {title}
      </div>

      <div className="mt-2 overflow-hidden rounded-lg border border-(--border-subtle)">
        <div className={`hidden bg-(--surface-2) text-[11px] font-bold uppercase tracking-wide text-(--text-muted) sm:grid ${grid}`}>
          <span className="px-2.5 py-1.5" />
          {columns.map((column) => (
            <span key={column} className="px-2.5 py-1.5 text-(--text-primary)">
              {column}
            </span>
          ))}
        </div>
        {rows.map((row) => (
          <div
            key={row.label}
            className={`grid border-t border-(--border-subtle) first:border-t-0 sm:border-t sm:first:border-t-0 ${grid} grid-cols-1`}
          >
            <span className="bg-(--surface-2) px-2.5 py-1.5 text-[11px] font-bold uppercase tracking-wide text-(--text-muted) sm:bg-transparent sm:py-2">
              {row.label}
            </span>
            {cells(row).map((cell, index) => (
              <p key={columns[index]} className="px-2.5 py-1.5 text-xs leading-relaxed text-(--text-primary) sm:py-2">
                <span className="mr-1 font-semibold text-(--section-chat) sm:hidden">{columns[index]}:</span>
                {cell}
              </p>
            ))}
          </div>
        ))}
      </div>

      <p className="mt-2 rounded-lg bg-(--section-chat-soft) px-2.5 py-2 text-xs leading-relaxed text-(--text-primary)">
        <span className="font-semibold">Simpler for a beginner: </span>
        {takeaway}
      </p>
    </div>
  );
}
