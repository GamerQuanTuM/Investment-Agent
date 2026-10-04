"use client";

import { useState } from "react";
import { BarChart3, TrendingUp, ShieldAlert, ExternalLink } from "lucide-react";
import { FundSearch } from "@/components/FundSearch";
import { fetchFundDetail, fundSipBacktest, fundSipProject } from "@/lib/api";
import { FundDetail, FundSipBacktestResult, FundSipProjectResult } from "@/lib/types";

const PROJECTION_SCENARIOS = [8, 10, 12];

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

function pct(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

export function FundSipPanel() {
  const [selected, setSelected] = useState<{ scheme_code: string; name: string } | null>(null);
  const [amount, setAmount] = useState(5000);
  const [years, setYears] = useState(10);
  const [stepUpPct, setStepUpPct] = useState(0);

  const [detail, setDetail] = useState<FundDetail | null>(null);
  const [backtest, setBacktest] = useState<FundSipBacktestResult | null>(null);
  const [projections, setProjections] = useState<Record<number, FundSipProjectResult> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!selected) return;
    setError(null);
    setBusy(true);
    try {
      const [detailResult, backtestResult, ...projectionResults] = await Promise.all([
        fetchFundDetail(selected.scheme_code),
        fundSipBacktest(selected.scheme_code, amount, stepUpPct),
        ...PROJECTION_SCENARIOS.map((rate) => fundSipProject(amount, years, rate, stepUpPct)),
      ]);
      setDetail(detailResult);
      setBacktest(backtestResult);
      setProjections(
        PROJECTION_SCENARIOS.reduce<Record<number, FundSipProjectResult>>((acc, rate, index) => {
          acc[rate] = projectionResults[index];
          return acc;
        }, {}),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze this fund. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="card p-5">
        <label className="text-sm font-semibold text-(--text-secondary)">Fund</label>
        <div className="mt-2">
          <FundSearch onSelect={(scheme) => setSelected(scheme)} />
        </div>
        {selected && (
          <p className="mt-2 text-xs text-(--text-secondary)">
            Selected: <span className="font-semibold text-(--text-primary)">{selected.name}</span>
          </p>
        )}

        <div className="mt-5 flex items-center justify-between">
          <label htmlFor="fund-sip-amount" className="text-sm font-semibold text-(--text-secondary)">Monthly investment</label>
          <span className="num-tabular text-lg font-bold text-(--section-sip)">₹{amount.toLocaleString("en-IN")}</span>
        </div>
        <input
          id="fund-sip-amount"
          type="range"
          min={100}
          max={100000}
          step={500}
          value={amount}
          onChange={(event) => setAmount(Number(event.target.value))}
          className="mt-2 w-full accent-(--section-sip)"
        />

        <div className="mt-5 flex items-center justify-between">
          <label htmlFor="fund-sip-years" className="text-sm font-semibold text-(--text-secondary)">Investment horizon</label>
          <span className="num-tabular text-lg font-bold text-(--section-sip)">{years} yrs</span>
        </div>
        <input
          id="fund-sip-years"
          type="range"
          min={1}
          max={30}
          value={years}
          onChange={(event) => setYears(Number(event.target.value))}
          className="mt-2 w-full accent-(--section-sip)"
        />

        <div className="mt-5 flex items-center justify-between">
          <label htmlFor="fund-sip-stepup" className="text-sm font-semibold text-(--text-secondary)">Annual step-up</label>
          <span className="num-tabular text-lg font-bold text-(--section-sip)">{stepUpPct}%</span>
        </div>
        <input
          id="fund-sip-stepup"
          type="range"
          min={0}
          max={25}
          value={stepUpPct}
          onChange={(event) => setStepUpPct(Number(event.target.value))}
          className="mt-2 w-full accent-(--section-sip)"
        />

        <button
          type="button"
          onClick={() => void run()}
          disabled={busy || !selected}
          className="mt-5 w-full rounded-xl bg-(--section-sip) py-2.5 text-sm font-semibold text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Analyzing…" : selected ? "Analyze this fund" : "Search and pick a fund first"}
        </button>
        {error && <p className="mt-3 text-sm text-(--bear-red)">{error}</p>}
      </div>

      <div className="flex flex-col gap-4">
        {detail && detail.status === "DATA_UNAVAILABLE" && (
          <div className="card p-5">
            <p className="text-sm text-(--text-secondary)">Data unavailable for this fund right now.</p>
          </div>
        )}

        {detail && detail.status === "OK" && (
          <div className="card p-5">
            <div className="flex items-center gap-2.5">
              <span className="icon-badge h-8 w-8 bg-(--section-sip-soft) text-(--section-sip)">
                <BarChart3 className="h-4 w-4" />
              </span>
              <h2 className="text-sm font-bold text-(--text-primary)">Fund facts</h2>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2.5 text-xs">
              {(["1y", "3y", "5y", "10y"] as const).map((key) => (
                <div key={key} className="card-row px-3 py-2">
                  <div className="text-(--text-secondary)">Trailing {key}</div>
                  <div className="num-tabular font-semibold text-(--text-primary)">
                    {pct(detail.trailing_returns_pct?.[key])}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2.5 grid grid-cols-2 gap-2.5 text-xs">
              <div className="card-row px-3 py-2">
                <div className="text-(--text-secondary)">Max drawdown</div>
                <div className="num-tabular font-semibold text-(--bear-red)">{pct(detail.risk?.max_drawdown_pct)}</div>
              </div>
              <div className="card-row px-3 py-2">
                <div className="text-(--text-secondary)">Volatility (ann.)</div>
                <div className="num-tabular font-semibold text-(--text-primary)">{pct(detail.risk?.annualized_volatility_pct)}</div>
              </div>
            </div>
            {detail.source_url && (
              <a
                href={detail.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 flex items-center gap-1.5 text-xs font-medium text-(--section-portfolio) hover:underline"
              >
                <ExternalLink className="h-3 w-3" /> {detail.source_name} · as of {detail.data_as_of}
              </a>
            )}
          </div>
        )}

        {backtest && (
          <div className="card p-5">
            <div className="flex items-center gap-2.5">
              <span className="icon-badge h-8 w-8 bg-(--bull-green-soft) text-(--bull-green)">
                <TrendingUp className="h-4 w-4" />
              </span>
              <h2 className="text-sm font-bold text-(--text-primary)">Historical backtest</h2>
            </div>
            {backtest.invested == null ? (
              <p className="mt-3 text-sm text-(--text-secondary)">
                Not enough NAV history to backtest this SIP.
              </p>
            ) : (
              <>
                <p className="mt-1 text-xs text-(--text-secondary)">
                  Had you started this SIP on {backtest.start_date}, this is what really happened to {backtest.end_date}.
                </p>
                <div className="mt-3 flex items-center justify-between text-xs">
                  <span className="text-(--text-secondary)">Invested</span>
                  <span className="num-tabular font-semibold text-(--text-primary)">{money(backtest.invested)}</span>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-xs">
                  <span className="text-(--text-secondary)">Current value</span>
                  <span className="num-tabular font-semibold text-(--bull-green)">{money(backtest.current_value)}</span>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-xs">
                  <span className="text-(--text-secondary)">XIRR</span>
                  <span className="num-tabular font-semibold text-(--text-primary)">{pct(backtest.xirr_pct)}</span>
                </div>
              </>
            )}
          </div>
        )}

        {projections && (
          <div className="card p-5">
            <div className="flex items-center gap-2.5">
              <span className="icon-badge h-8 w-8 bg-(--section-gold-soft) text-(--section-gold)">
                <ShieldAlert className="h-4 w-4" />
              </span>
              <h2 className="text-sm font-bold text-(--text-primary)">Forward projection</h2>
            </div>
            <p className="mt-1 text-xs text-(--text-secondary)">
              {projections[PROJECTION_SCENARIOS[0]].assumption_note}
            </p>
            <div className="mt-3 space-y-2">
              {PROJECTION_SCENARIOS.map((rate) => (
                <div key={rate} className="card-row flex items-center justify-between px-3.5 py-2.5">
                  <span className="text-xs font-semibold text-(--text-secondary)">{rate}% assumption</span>
                  <span className="num-tabular text-sm font-semibold text-(--text-primary)">
                    {money(projections[rate].nominal_corpus)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
