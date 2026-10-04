"use client";

import { useMemo, useState } from "react";
import { PiggyBank, Wallet, TrendingUp, Landmark, Sparkles as SparklesIcon } from "lucide-react";
import { planSip, SipPlan } from "@/lib/api";
import { FundSipPanel } from "@/components/FundSipPanel";
import { RegisteredFunds } from "@/components/RegisteredFunds";
import { SuggestMixPanel } from "@/components/SuggestMixPanel";

const STYLES = [
  { id: "large", label: "Large cap" },
  { id: "flexi", label: "Flexi cap" },
  { id: "mid", label: "Mid cap" },
  { id: "small", label: "Small cap" },
];

const ASSUMED_ANNUAL_RETURN_PCT = 12;

const MODES = [
  { id: "fund", label: "Mutual fund", icon: Landmark, hint: "Backtest and project a SIP in a real fund using its NAV history." },
  { id: "suggest", label: "Suggest a mix", icon: SparklesIcon, hint: "Get a fund mix matched to your horizon and comfort with risk." },
  { id: "etf", label: "ETF mix", icon: PiggyBank, hint: "Listed ETFs bought through your broker at the live price." },
] as const;

type Mode = (typeof MODES)[number]["id"];

function projectSip(monthly: number, years: number, annualReturnPct: number) {
  const months = years * 12;
  const r = annualReturnPct / 100 / 12;
  const invested = monthly * months;
  const futureValue = r === 0 ? invested : monthly * ((Math.pow(1 + r, months) - 1) / r) * (1 + r);
  return { invested, futureValue, gains: Math.max(futureValue - invested, 0) };
}

export default function SipPage() {
  const [mode, setMode] = useState<Mode>("fund");
  const [amount, setAmount] = useState(10000);
  const [years, setYears] = useState(10);
  const [style, setStyle] = useState("flexi");
  const [plan, setPlan] = useState<SipPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const projection = useMemo(() => projectSip(amount, years, ASSUMED_ANNUAL_RETURN_PCT), [amount, years]);
  const gainsSharePct = projection.futureValue > 0 ? Math.round((projection.gains / projection.futureValue) * 100) : 0;
  const money = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

  const run = async () => {
    setError(null);
    setBusy(true);
    try {
      setPlan(await planSip(amount, years, style));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build a SIP mix. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const activeMode = MODES.find((item) => item.id === mode)!;

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-4 lg:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-9 w-9 bg-(--section-sip-soft) text-(--section-sip)">
            <PiggyBank className="h-4.5 w-4.5" />
          </span>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-(--text-primary)">SIP planner</h1>
            <p className="text-xs text-(--text-secondary)">{activeMode.hint}</p>
          </div>
        </div>
        <div role="tablist" aria-label="SIP mode" className="grid grid-cols-3 gap-1 rounded-2xl border border-(--border-subtle) bg-(--surface-2) p-1">
          {MODES.map((item) => {
            const Icon = item.icon;
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setMode(item.id)}
                className={`flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
                  active
                    ? "bg-(--section-sip) text-white shadow-(--shadow-card)"
                    : "text-(--text-secondary) hover:bg-(--surface-3)"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="sip-workspace mt-4 grid min-h-128 flex-1 items-stretch gap-4 lg:grid-cols-[minmax(18rem,24rem)_minmax(0,1fr)]">
      <div className="min-h-0 min-w-0 lg:overflow-y-auto lg:pr-1">
      {mode === "fund" && <FundSipPanel />}

      {mode === "suggest" && <SuggestMixPanel />}

      {mode === "etf" && (
      <>
      <p className="rounded-xl border border-(--border-subtle) bg-(--surface-2) p-3 text-xs text-(--text-secondary)">
        This buys listed ETFs through your broker (a market order at the live price), not a mutual-fund SIP through
        the AMC/RTA — the two run through different mechanisms. For a real mutual fund with NAV-based backtesting,
        use the <strong className="text-(--text-primary)">Mutual fund</strong> tab instead.
      </p>
      <div className="grid grid-cols-1 gap-4">
        {/* Calculator inputs */}
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <label htmlFor="sip-amount" className="text-sm font-semibold text-(--text-secondary)">Monthly investment</label>
            <span className="num-tabular text-lg font-bold text-(--section-sip)">₹{amount.toLocaleString("en-IN")}</span>
          </div>
          <input
            id="sip-amount"
            type="range"
            min={500}
            max={100000}
            step={500}
            value={amount}
            onChange={(event) => setAmount(Number(event.target.value))}
            className="mt-2 w-full accent-(--section-sip)"
          />

          <div className="mt-5 flex items-center justify-between">
            <label htmlFor="sip-years" className="text-sm font-semibold text-(--text-secondary)">Investment horizon</label>
            <span className="num-tabular text-lg font-bold text-(--section-sip)">{years} yrs</span>
          </div>
          <input
            id="sip-years"
            type="range"
            min={1}
            max={30}
            value={years}
            onChange={(event) => setYears(Number(event.target.value))}
            className="mt-2 w-full accent-(--section-sip)"
          />

          <div className="mt-5">
            <span className="text-sm font-semibold text-(--text-secondary)">Cap style</span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {STYLES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setStyle(item.id)}
                  className={`nav-pill px-3.5 py-1.5 text-xs font-semibold ${
                    style === item.id
                      ? "bg-(--section-sip) text-white"
                      : "bg-(--surface-2) text-(--text-secondary) hover:bg-(--surface-3)"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={() => void run()}
            disabled={busy}
            className="mt-5 w-full rounded-xl bg-(--section-sip) py-2.5 text-sm font-semibold text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "Building…" : "Build my SIP mix"}
          </button>
          {error && <p className="mt-3 text-sm text-(--bear-red)">{error}</p>}
        </div>

        {/* Projection */}
        <div className="card flex flex-col justify-between p-5">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="icon-badge h-9 w-9 bg-(--bull-green-soft) text-(--bull-green)">
                <TrendingUp className="h-4.5 w-4.5" />
              </span>
              <h2 className="text-sm font-bold text-(--text-primary)">Projected corpus</h2>
            </div>
            <div className="num-tabular mt-4 text-3xl font-bold text-(--text-primary)">{money(projection.futureValue)}</div>
            <p className="mt-1 text-xs text-(--text-secondary)">At an assumed {ASSUMED_ANNUAL_RETURN_PCT}% annual return, illustrative only.</p>

            <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-(--section-sip-soft)">
              <div className="h-full rounded-full bg-(--section-sip)" style={{ width: `${100 - gainsSharePct}%` }} />
            </div>
            <div className="mt-3 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-(--text-secondary)">
                <span className="h-2 w-2 rounded-full bg-(--section-sip)" /> Invested
              </span>
              <span className="num-tabular font-semibold text-(--text-primary)">{money(projection.invested)}</span>
            </div>
            <div className="mt-1.5 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-(--text-secondary)">
                <span className="h-2 w-2 rounded-full bg-(--bull-green)" /> Est. gains
              </span>
              <span className="num-tabular font-semibold text-(--bull-green)">{money(projection.gains)}</span>
            </div>
          </div>
        </div>
      </div>

      <div aria-live="polite">
        {plan && (
          <section className="card mt-5 p-5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <span className="icon-badge h-9 w-9 bg-(--section-sip-soft) text-(--section-sip)">
                  <Wallet className="h-4.5 w-4.5" />
                </span>
                <h2 className="text-sm font-bold text-(--text-primary)">Your monthly mix</h2>
              </div>
              {plan.style !== plan.requested_style && (
                <span className="flex items-center gap-1 rounded-full bg-(--section-chat-soft) px-2.5 py-1 text-[11px] font-semibold text-(--section-chat)">
                  Adjusted to {plan.style} cap for this horizon
                </span>
              )}
            </div>
            <div className="mt-3 space-y-2">
              {plan.sleeves.map((row) => (
                <div key={row.symbol} className="card-row flex items-center justify-between px-3.5 py-3">
                  <div>
                    <div className="font-semibold text-(--text-primary)">{row.symbol}</div>
                    <div className="text-xs text-(--text-secondary)">
                      {row.label} · {row.weight_pct}%
                      {row.live_price != null && ` · NAV ₹${row.live_price.toLocaleString("en-IN")}`}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="num-tabular font-semibold text-(--section-sip)">₹{row.monthly_inr.toLocaleString("en-IN")}/mo</div>
                    {row.units != null && <div className="num-tabular text-[11px] text-(--text-secondary)">≈ {row.units} units</div>}
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-(--text-secondary)">{plan.note}</p>
          </section>
        )}
      </div>
      </>
      )}
      </div>
      <RegisteredFunds />
      </div>
    </main>
  );
}
