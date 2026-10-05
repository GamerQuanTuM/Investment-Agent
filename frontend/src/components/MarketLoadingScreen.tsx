"use client";

import { useEffect, useState } from "react";

const STEPS = ["Connecting to INDstocks", "Fetching live prices", "Crunching the numbers"];

export function MarketLoadingScreen({ label = "Fetching live prices from INDstocks" }: { label?: string }) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1800);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-(--bg-base)"
    >
      {/* soft ambient glow */}
      <div className="pointer-events-none absolute -top-40 left-1/2 h-120 w-120 -translate-x-1/2 rounded-full bg-(--brand-soft) opacity-80 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-48 right-[-6rem] h-104 w-104 rounded-full bg-(--section-gold-soft) opacity-90 blur-3xl" />

      <div className="relative flex w-full max-w-sm flex-col items-center px-6 text-center">
        {/* orbiting logo */}
        <div className="relative flex h-32 w-32 items-center justify-center">
          <span className="ml-ring absolute inset-0 rounded-full border border-(--brand)/25" />
          <span
            className="ml-ring absolute inset-0 rounded-full border border-(--brand)/25"
            style={{ animationDelay: "1s" }}
          />
          <span className="ml-spin absolute inset-2 rounded-full border-2 border-transparent border-t-(--brand) border-r-(--brand)/30" />
          <span className="relative flex h-18 w-18 items-center justify-center rounded-3xl border border-(--border-subtle) bg-white text-4xl font-bold text-(--section-gold) shadow-(--shadow-pop)">
            ₹
          </span>
        </div>

        <h1 className="mt-8 text-2xl font-bold tracking-tight text-(--text-primary)">MudraLens</h1>
        <p className="mt-1.5 text-sm text-(--text-secondary)">{label}</p>

        {/* progress bar */}
        <div className="mt-6 h-1.5 w-56 overflow-hidden rounded-full bg-(--surface-3)">
          <div className="ml-bar h-full w-2/5 rounded-full bg-linear-to-r from-(--brand) to-(--section-chat)" />
        </div>

        {/* steps */}
        <ul className="mt-6 space-y-2 text-left text-sm">
          {STEPS.map((text, i) => {
            const done = i < step;
            const active = i === step;
            return (
              <li
                key={text}
                className={`flex items-center gap-2.5 transition-colors duration-500 ${
                  done || active ? "text-(--text-primary)" : "text-(--text-muted)"
                }`}
              >
                <span
                  className={`flex h-4.5 w-4.5 items-center justify-center rounded-full text-[10px] font-bold transition-all duration-500 ${
                    done
                      ? "bg-(--bull-green) text-white"
                      : active
                        ? "ml-dot bg-(--brand-soft) text-(--brand)"
                        : "bg-(--surface-3)"
                  }`}
                >
                  {done ? "✓" : active ? "●" : ""}
                </span>
                {text}
              </li>
            );
          })}
        </ul>
      </div>

      <style>{`
        @keyframes ml-ring { 0% { transform: scale(.7); opacity: .9; } 100% { transform: scale(1.35); opacity: 0; } }
        @keyframes ml-spin { to { transform: rotate(360deg); } }
        @keyframes ml-bar { 0% { transform: translateX(-110%); } 100% { transform: translateX(260%); } }
        @keyframes ml-dot { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
        .ml-ring { animation: ml-ring 2s ease-out infinite; }
        .ml-spin { animation: ml-spin 1.1s linear infinite; }
        .ml-bar { animation: ml-bar 1.4s ease-in-out infinite; }
        .ml-dot { animation: ml-dot 1.2s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .ml-ring, .ml-spin, .ml-bar, .ml-dot { animation: none; }
        }
      `}</style>
    </div>
  );
}
