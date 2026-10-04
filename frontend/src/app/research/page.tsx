"use client";

import { FormEvent, useState } from "react";
import {
  FlaskConical,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Wallet,
  ShoppingCart,
  Gauge,
  Sparkles,
} from "lucide-react";
import { fetchGuidance } from "@/lib/api";
import { GuidanceNote } from "@/lib/types";

const tone: Record<GuidanceNote["stance"], string> = {
  CONSIDER: "text-(--bull-green) bg-(--bull-green-soft)",
  WAIT: "text-(--section-gold) bg-(--section-gold-soft)",
  AVOID: "text-(--bear-red) bg-(--bear-red-soft)",
};

const riskTone: Record<"LOW" | "MEDIUM" | "HIGH", string> = {
  LOW: "text-(--bull-green) bg-(--bull-green-soft)",
  MEDIUM: "text-(--section-gold) bg-(--section-gold-soft)",
  HIGH: "text-(--bear-red) bg-(--bear-red-soft)",
};

const stanceInPlainWords: Record<GuidanceNote["stance"], string> = {
  CONSIDER: "Looks worth considering",
  WAIT: "Not clear yet — wait for more info",
  AVOID: "Better to avoid for now",
};

export default function ResearchPage() {
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [years, setYears] = useState(5);
  const [months, setMonths] = useState(0);
  const [budget, setBudget] = useState(25000);
  const [note, setNote] = useState<GuidanceNote | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (event: FormEvent) => {
    event.preventDefault();
    const ticker = symbol.trim().toUpperCase();
    if (!ticker) {
      setError("Enter the stock symbol you want researched.");
      return;
    }
    if (years === 0 && months === 0) {
      setError("Enter a holding span in years, months, or both.");
      return;
    }
    if (!budget || budget <= 0) {
      setError("Enter a monthly amount greater than zero.");
      return;
    }
    setLoading(true);
    setError(null);
    setNote(null);
    try {
      setNote(await fetchGuidance(ticker, years, budget, exchange, months));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-4xl px-4 py-6">
      <div className="flex items-center gap-2.5">
        <span className="icon-badge h-9 w-9 bg-(--section-research-soft) text-(--section-research)">
          <FlaskConical className="h-4.5 w-4.5" />
        </span>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-(--text-primary)">Research a stock</h1>
          <p className="text-sm text-(--text-secondary)">
            Name the share, the exchange, how long you will hold it, and the monthly amount.
          </p>
        </div>
      </div>

      <form onSubmit={(event) => void run(event)} className="card mt-5 grid gap-4 p-5 sm:grid-cols-2">
        <label className="text-sm font-semibold text-(--text-secondary)">
          Symbol
          <input
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            placeholder="TCS"
            required
            className="mt-1 w-full rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2.5 text-sm font-semibold text-(--text-primary) outline-none focus:border-(--section-research)"
          />
        </label>
        <div>
          <span className="text-sm font-semibold text-(--text-secondary)">Exchange</span>
          <div className="mt-1 flex gap-2">
            {(["NSE", "BSE"] as const).map((venue) => (
              <button
                key={venue}
                type="button"
                onClick={() => setExchange(venue)}
                className={`nav-pill px-4 py-2 text-xs font-semibold ${
                  exchange === venue ? "bg-(--section-research) text-white" : "bg-(--surface-2) text-(--text-secondary)"
                }`}
              >
                {venue}
              </button>
            ))}
          </div>
        </div>
        <label className="text-sm font-semibold text-(--text-secondary)">
          Holding span
          <span className="mt-1 flex gap-2">
            <input
              type="number"
              min={0}
              max={30}
              value={years}
              onChange={(event) => setYears(Number(event.target.value))}
              aria-label="Holding span in years"
              className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2.5 text-sm text-(--text-primary) outline-none focus:border-(--section-research)"
            />
            <span className="self-center text-xs font-medium text-(--text-muted)">years</span>
            <input
              type="number"
              min={0}
              max={11}
              value={months}
              onChange={(event) => setMonths(Number(event.target.value))}
              aria-label="Holding span in months"
              className="w-full rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2.5 text-sm text-(--text-primary) outline-none focus:border-(--section-research)"
            />
            <span className="self-center text-xs font-medium text-(--text-muted)">months</span>
          </span>
        </label>
        <label className="text-sm font-semibold text-(--text-secondary)">
          Monthly amount
          <input
            type="number"
            min={1}
            step={1}
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
            className="mt-1 w-full rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 py-2.5 text-sm text-(--text-primary) outline-none focus:border-(--section-research)"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-xl bg-(--section-research) px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60 sm:col-span-2"
        >
          {loading ? "Researching live quote…" : "Research this stock"}
        </button>
      </form>

      <div aria-live="polite" className="mt-5 space-y-4">
        {error && (
          <div className="card-row flex items-center gap-2 p-4 text-sm text-(--bear-red)">
            <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
          </div>
        )}
        {note && (
          <article className="card overflow-hidden p-0">
            {/* Beginner verdict — plain English, no jargon */}
            <div className={`p-5 ${note.stance === "AVOID" ? "bg-(--bear-red-soft)" : note.stance === "CONSIDER" ? "bg-(--bull-green-soft)" : "bg-(--section-gold-soft)"}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <span className="icon-badge h-10 w-10 bg-(--surface-1) text-(--section-research)">
                    <Sparkles className="h-5 w-5" />
                  </span>
                  <div>
                    <h2 className="text-lg font-bold text-(--text-primary)">
                      {note.symbol} <span className="text-sm font-medium text-(--text-secondary)">{note.name}</span>
                    </h2>
                    <p className="text-sm font-semibold text-(--text-primary)">{stanceInPlainWords[note.stance]}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {note.risk_level && (
                    <span className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-bold ${riskTone[note.risk_level]}`}>
                      <Gauge className="h-3.5 w-3.5" /> {note.risk_level} risk
                    </span>
                  )}
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${tone[note.stance]}`}>{note.stance}</span>
                </div>
              </div>

              <p className="mt-4 text-sm leading-relaxed text-(--text-primary)">
                {note.verdict_explanation || note.summary}
              </p>

              {/* How much to invest / how many shares */}
              <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                <div className="flex items-center gap-2.5 rounded-xl bg-(--surface-1) p-3">
                  <span className="icon-badge h-9 w-9 bg-(--section-portfolio-soft) text-(--section-portfolio)">
                    <Wallet className="h-4.5 w-4.5" />
                  </span>
                  <div>
                    <div className="text-[11px] text-(--text-secondary)">How much you said you&apos;d invest</div>
                    <div className="num-tabular text-sm font-bold text-(--text-primary)">₹{budget.toLocaleString("en-IN")} / month</div>
                  </div>
                </div>
                <div className="flex items-center gap-2.5 rounded-xl bg-(--surface-1) p-3">
                  <span className="icon-badge h-9 w-9 bg-(--section-sip-soft) text-(--section-sip)">
                    <ShoppingCart className="h-4.5 w-4.5" />
                  </span>
                  <div>
                    <div className="text-[11px] text-(--text-secondary)">Shares that money buys today</div>
                    <div className="num-tabular text-sm font-bold text-(--text-primary)">
                      {note.shares_to_buy ? `${note.shares_to_buy} share${note.shares_to_buy === 1 ? "" : "s"}` : "Not enough for 1 share"}
                      {note.leftover_cash != null && note.leftover_cash > 0 && (
                        <span className="ml-1 text-xs font-normal text-(--text-secondary)">(₹{note.leftover_cash.toLocaleString("en-IN")} left over)</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Why it's good / why it's risky, in plain language */}
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-(--surface-1) p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-(--bull-green)">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Why it could be good
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {(note.good_points || []).map((item) => (
                      <li key={item} className="flex gap-1.5 text-sm text-(--text-primary)">
                        <span className="text-(--bull-green)">•</span> {item}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl bg-(--surface-1) p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-(--bear-red)">
                    <XCircle className="h-3.5 w-3.5" /> Why it could be risky
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {(note.bad_points || []).map((item) => (
                      <li key={item} className="flex gap-1.5 text-sm text-(--text-primary)">
                        <span className="text-(--bear-red)">•</span> {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* Technical detail, for readers who want the raw numbers */}
            <div className="border-t border-(--border-subtle) p-5">
              <h3 className="text-xs font-bold uppercase tracking-wide text-(--text-muted)">Technical detail</h3>
              <p className="mt-2 num-tabular text-sm text-(--text-secondary)">
                {note.live_price != null && `₹${note.live_price.toLocaleString("en-IN")}`}
                {note.pe_ratio != null ? ` · P/E ${note.pe_ratio}` : " · P/E not on the quote"}
                {note.one_year_price_change_pct != null && ` · 1Y ${note.one_year_price_change_pct}%`}
                {` · ${years}y ${months}m · ₹${budget.toLocaleString("en-IN")}/month`}
              </p>
            <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                ["ROE", note.fundamentals?.roe_pct, "%"],
                ["ROIC", note.fundamentals?.roic_pct, "%"],
                ["Debt / equity", note.fundamentals?.debt_to_equity, ""],
                ["Revenue growth", note.fundamentals?.revenue_growth_pct, "%"],
                ["Profit growth", note.fundamentals?.earnings_growth_pct, "%"],
                ["Net margin", note.fundamentals?.profit_margin_pct, "%"],
                ["Operating margin", note.fundamentals?.operating_margin_pct, "%"],
                ["Price / book", note.fundamentals?.price_to_book, ""],
                ["Dividend yield", note.fundamentals?.dividend_yield_pct, "%"],
                ["EPS", note.fundamentals?.eps, ""],
                ["Book value", note.fundamentals?.book_value, ""],
              ].map(([label, value, unit]) => (
                <div key={String(label)} className="rounded-lg bg-(--surface-2) px-3 py-2">
                  <dt className="text-[11px] text-(--text-muted)">{label}</dt>
                  <dd className="num-tabular text-sm font-semibold text-(--text-primary)">
                    {value == null || value === "" ? "—" : `${value}${unit}`}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-[11px] text-(--text-muted)">
              {String(note.fundamentals?.sector || "Sector unavailable")}
              {note.fundamentals?.industry ? ` · ${note.fundamentals.industry}` : ""}. Source: Yahoo Finance and TradingView. Promoter holding and pledge are not included.
            </p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-(--text-secondary)">
              {note.reasons.map((item) => (
                <li key={item}>{item}</li>
              ))}
              {note.blockers.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            </div>
          </article>
        )}
      </div>
    </main>
  );
}
