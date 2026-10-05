"use client";

import { useState } from "react";
import { BookOpen } from "lucide-react";
import { GlossaryEntry } from "@/lib/types";

/** Compact definition card; the rupee example stays tucked behind a "Try an example" chip. */
export function GlossaryCard({ entry }: { entry: GlossaryEntry }) {
  const [showExample, setShowExample] = useState(false);
  return (
    <div className="rounded-xl border border-(--border-subtle) bg-(--surface-1) p-3">
      <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-(--section-chat)">
        <BookOpen className="h-3.5 w-3.5" />
        {entry.term}
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-(--text-primary)">{entry.definition}</p>
      {showExample ? (
        <p className="mt-2 rounded-lg bg-(--section-chat-soft) px-2.5 py-2 text-xs leading-relaxed text-(--text-primary)">
          <span className="font-semibold">Example: </span>
          {entry.example}
        </p>
      ) : (
        <button
          type="button"
          onClick={() => setShowExample(true)}
          className="nav-pill mt-2 border border-(--border-subtle) bg-(--surface-2) px-3 py-1 text-xs text-(--text-secondary) transition-colors hover:bg-(--surface-3) hover:text-(--text-primary)"
        >
          Try an example
        </button>
      )}
    </div>
  );
}
