"use client";

import { Check, ChevronDown, Globe, Loader2 } from "lucide-react";
import { ResearchStep } from "@/lib/types";

/** Insert or update a step by id, keeping the order steps first appeared in. */
export function mergeStep(steps: ResearchStep[], step: ResearchStep): ResearchStep[] {
  const index = steps.findIndex((s) => s.id === step.id);
  if (index === -1) return [...steps, step];
  const next = steps.slice();
  next[index] = step;
  return next;
}

function StepList({ steps }: { steps: ResearchStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((step) => (
        <li key={step.id} className="flex items-start gap-2.5 text-sm">
          <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
            {step.status === "done" ? (
              <Check className="h-4 w-4 text-(--bull-green)" aria-label="done" />
            ) : (
              <Loader2 className="h-4 w-4 animate-spin text-(--section-chat)" aria-label="in progress" />
            )}
          </span>
          <span className="min-w-0">
            <span className={step.status === "done" ? "text-(--text-secondary)" : "font-medium text-(--text-primary)"}>
              {step.label}
            </span>
            {step.detail && <span className="block truncate text-xs text-(--text-muted)">{step.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Live checklist while the agent researches (ChatGPT-style), shown in place of the typing dots. */
export function ResearchProgress({ steps, label = "Researching" }: { steps: ResearchStep[]; label?: string }) {
  return (
    <div
      className="card-row w-full max-w-md space-y-3 border border-(--section-chat)/25 px-4 py-3"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-(--text-primary)">
        <Globe className="h-4 w-4 animate-pulse text-(--section-chat)" />
        {label}…
      </div>
      {steps.length > 0 ? (
        <StepList steps={steps} />
      ) : (
        <div className="flex items-center gap-1.5 text-(--text-muted)">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
        </div>
      )}
    </div>
  );
}

/** After the answer: a collapsed "Researched for 18s" line the user can open to see what was done. */
export function ResearchSummary({ steps, seconds }: { steps: ResearchStep[]; seconds?: number }) {
  if (steps.length === 0) return null;
  return (
    <details className="group mb-2 rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-semibold text-(--text-secondary)">
        <Globe className="h-3.5 w-3.5 text-(--section-chat)" />
        Researched{seconds != null ? ` for ${Math.max(1, Math.round(seconds))}s` : ""} · {steps.length} step
        {steps.length === 1 ? "" : "s"}
        <ChevronDown className="ml-auto h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-2.5 border-t border-(--border-subtle) pt-2.5">
        <StepList steps={steps.map((s) => ({ ...s, status: "done" as const }))} />
      </div>
    </details>
  );
}
