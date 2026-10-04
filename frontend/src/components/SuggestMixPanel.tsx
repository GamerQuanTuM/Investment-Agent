"use client";

import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { suggestFundMix } from "@/lib/api";
import { SuggestMixResult } from "@/lib/types";

const RISK_PROFILES = [
  { id: "conservative", label: "Conservative" },
  { id: "moderate", label: "Moderate" },
  { id: "aggressive", label: "Aggressive" },
];

const CATEGORY_COLORS: Record<string, string> = {
  debt: "#0891b2",
  "large cap": "#2f6fed",
  "flexi cap": "#8b5cf6",
  "mid cap": "#f0802a",
  "small cap": "#e5484d",
  gold: "#d4932a",
};

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

export function SuggestMixPanel() {
  const [amount, setAmount] = useState(10000);
  const [years, setYears] = useState(10);
  const [riskProfile, setRiskProfile] = useState("moderate");
  const [spanYears, setSpanYears] = useState(0);
  const [spanMonths, setSpanMonths] = useState(6);
  const [result, setResult] = useState<SuggestMixResult | null>(null);
  const [fundsOpen, setFundsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!fundsOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFundsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fundsOpen]);

  const run = async () => {
    if (spanYears === 0 && spanMonths === 0) {
      setError("Enter at least one month to compare returns.");
      return;
    }
    setError(null);
    setResult(null);
    setFundsOpen(false);
    setBusy(true);
    try {
      setResult(await suggestFundMix(amount, years, riskProfile, spanYears, spanMonths));
      setFundsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build a suggestion. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <label htmlFor="suggest-amount" className="text-sm font-semibold text-(--text-secondary)">Monthly investment</label>
          <span className="num-tabular text-lg font-bold text-(--section-sip)">₹{amount.toLocaleString("en-IN")}</span>
        </div>
        <input
          id="suggest-amount"
          type="range"
          min={500}
          max={100000}
          step={500}
          value={amount}
          onChange={(event) => setAmount(Number(event.target.value))}
          className="mt-2 w-full accent-(--section-sip)"
        />

        <div className="mt-5 flex items-center justify-between">
          <label htmlFor="suggest-years" className="text-sm font-semibold text-(--text-secondary)">Investment horizon</label>
          <span className="num-tabular text-lg font-bold text-(--section-sip)">{years} yrs</span>
        </div>
        <input
          id="suggest-years"
          type="range"
          min={1}
          max={30}
          value={years}
          onChange={(event) => setYears(Number(event.target.value))}
          className="mt-2 w-full accent-(--section-sip)"
        />

        <div className="mt-5">
          <span className="text-sm font-semibold text-(--text-secondary)">Compare returns over</span>
          <div className="mt-2 flex gap-2">
            <label className="flex flex-1 items-center gap-2">
              <input
                type="number"
                min={0}
                max={30}
                value={spanYears}
                onChange={(event) => setSpanYears(Number(event.target.value))}
                aria-label="Return span in years"
                className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2.5 text-sm outline-none focus:border-(--section-sip)"
              />
              <span className="text-xs font-medium text-(--text-muted)">years</span>
            </label>
            <label className="flex flex-1 items-center gap-2">
              <input
                type="number"
                min={0}
                max={11}
                value={spanMonths}
                onChange={(event) => setSpanMonths(Number(event.target.value))}
                aria-label="Return span in months"
                className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2.5 text-sm outline-none focus:border-(--section-sip)"
              />
              <span className="text-xs font-medium text-(--text-muted)">months</span>
            </label>
          </div>
        </div>

        <div className="mt-5">
          <span className="text-sm font-semibold text-(--text-secondary)">Risk profile</span>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {RISK_PROFILES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setRiskProfile(item.id)}
                className={`nav-pill px-3.5 py-1.5 text-xs font-semibold ${
                  riskProfile === item.id
                    ? "bg-(--section-sip) text-white"
                    : "bg-(--surface-2) text-(--text-secondary) hover:bg-(--surface-3)"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          {years < 3 && riskProfile !== "conservative" && (
            <p className="mt-2 text-xs text-(--text-secondary)">
              A horizon under 3 years overrides this to a conservative mix regardless — not enough time to ride out
              mid/small-cap swings.
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          className="mt-5 w-full rounded-xl bg-(--section-sip) py-2.5 text-sm font-semibold text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Comparing live returns…" : "Suggest a mix"}
        </button>
        {error && <p className="mt-3 text-sm text-(--bear-red)">{error}</p>}
      </div>

      <div className="flex flex-col gap-4">
        {result && (
          <>
            <div className="card p-5">
              <div className="flex items-center gap-2.5">
                <span className="icon-badge h-8 w-8 bg-(--section-sip-soft) text-(--section-sip)">
                  <Sparkles className="h-4 w-4" />
                </span>
                <h2 className="text-sm font-bold text-(--text-primary)">Suggested weights</h2>
              </div>
              <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full">
                {result.sleeves.map((sleeve) => (
                  <div
                    key={sleeve.category}
                    style={{
                      width: `${sleeve.weight_pct}%`,
                      backgroundColor: CATEGORY_COLORS[sleeve.category] ?? "#94a0b8",
                    }}
                  />
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
                {result.sleeves.map((sleeve) => (
                  <span key={sleeve.category} className="flex items-center gap-1.5 text-(--text-secondary)">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: CATEGORY_COLORS[sleeve.category] ?? "#94a0b8" }}
                    />
                    {sleeve.category} · {sleeve.weight_pct}%
                  </span>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => setFundsOpen(true)}
              className="w-full rounded-xl border border-(--section-sip) bg-(--section-sip-soft) py-2.5 text-sm font-semibold text-(--section-sip) mb-5"
            >
              View funds
            </button>
          </>
        )}
      </div>

      {fundsOpen && result && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setFundsOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="fund-mix-title"
            className="card max-h-[min(40rem,85vh)] w-full max-w-lg overflow-y-auto p-5"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="fund-mix-title" className="text-sm font-bold text-(--text-primary)">Funds in this mix</h2>
                <p className="mt-1 text-xs text-(--text-secondary)">
                  Top five Direct Growth schemes in each category, ranked by return over {result.return_span_label}.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setFundsOpen(false)}
                aria-label="Close"
                className="rounded-full p-1 text-(--text-secondary) hover:bg-(--surface-3)"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              {result.sleeves.map((sleeve) => (
                <section key={sleeve.category}>
                  <div className="flex items-baseline justify-between gap-3">
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-(--text-muted)">{sleeve.category}</h3>
                      {sleeve.category_label && (
                        <p className="text-[11px] italic text-(--text-muted)">{sleeve.category_label}</p>
                      )}
                    </div>
                    <p className="num-tabular text-sm font-semibold text-(--section-sip)">{money(sleeve.monthly_inr)}/mo</p>
                  </div>
                  {sleeve.funds && sleeve.funds.length > 0 ? (
                    <ol className="mt-2 space-y-2">
                      {sleeve.funds.map((fund, index) => (
                        <li key={fund.scheme_code} className="card-row px-3 py-2.5">
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-sm font-semibold text-(--text-primary)">
                              <span className="mr-1.5 text-xs text-(--text-muted)">{index + 1}.</span>
                              {fund.scheme_name}
                            </p>
                            <p className="num-tabular shrink-0 text-xs font-semibold text-(--text-secondary)">
                              {fund.trailing_return_pct_used.toFixed(1)}%
                            </p>
                          </div>
                          <p className="mt-1 text-[11px] text-(--text-secondary)">over {fund.return_window}</p>
                          {index === 0 && sleeve.projected_corpus != null && (
                            <p className="mt-1 text-[11px] text-(--text-secondary)">
                              Used in the mix · projected {money(sleeve.projected_corpus)}
                            </p>
                          )}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mt-2 text-xs text-(--section-gold)">No fund in this category covered that span.</p>
                  )}
                </section>
              ))}
            </div>
            {result.explanation && <p className="mt-4 text-xs text-(--text-secondary)">{result.explanation}</p>}
            <p className="mt-2 text-[11px] text-(--text-muted)">{result.note}</p>
          </div>
        </div>
      )}
    </div>
  );
}
