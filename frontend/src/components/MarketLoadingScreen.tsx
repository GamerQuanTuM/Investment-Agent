"use client";

export function MarketLoadingScreen({ label = "Fetching live prices from INDstocks" }: { label?: string }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#f6f7fb]">
      <div className="flex flex-col items-center px-6 text-center">
        <div className="relative flex h-28 w-28 items-center justify-center">
          <span className="absolute inset-0 animate-ping rounded-full border border-(--section-gold)/30" />
          <span className="absolute inset-3 animate-pulse rounded-full border border-(--section-gold)/40" />
          <span className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-(--border-subtle) bg-(--section-gold-soft) text-3xl font-bold text-(--section-gold) shadow-(--shadow-pop)">
            ₹
          </span>
        </div>
        <h1 className="mt-8 text-xl font-bold tracking-tight text-(--text-primary)">MudraLens</h1>
        <p className="mt-2 max-w-sm text-sm text-(--text-secondary)">{label}</p>
        <div className="mt-6 h-1 w-48 overflow-hidden rounded-full bg-(--surface-3)">
          <div className="h-full w-1/2 animate-[loading_1.4s_ease-in-out_infinite] rounded-full bg-(--section-gold)" />
        </div>
      </div>
      <style>{`
        @keyframes loading {
          0% { transform: translateX(-120%); }
          100% { transform: translateX(220%); }
        }
      `}</style>
    </div>
  );
}
