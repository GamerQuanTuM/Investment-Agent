"use client";

import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { fetchFundCatalogue } from "@/lib/api";

const CATEGORY_TONE: Record<string, string> = {
  "Large cap": "bg-(--brand-soft) text-(--brand)",
  "Large & mid": "bg-(--brand-soft) text-(--brand)",
  "Mid cap": "bg-(--section-gold-soft) text-(--section-gold)",
  "Small cap": "bg-(--bear-red-soft) text-(--bear-red)",
  "Flexi cap": "bg-(--section-sip-soft) text-(--section-sip)",
  Equity: "bg-(--bull-green-soft) text-(--bull-green)",
  Debt: "bg-(--section-chat-soft) text-(--section-chat)",
  Index: "bg-(--surface-3) text-(--text-secondary)",
  ELSS: "bg-(--section-research-soft) text-(--section-research)",
  Hybrid: "bg-(--section-portfolio-soft) text-(--section-portfolio)",
  Gold: "bg-(--section-gold-soft) text-(--section-gold)",
  Solution: "bg-(--section-chat-soft) text-(--section-chat)",
  Other: "bg-(--surface-3) text-(--text-muted)",
};

export function RegisteredFunds() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [tag, setTag] = useState("");
  const sentinel = useRef<HTMLDivElement | null>(null);

  const catalogue = useInfiniteQuery({
    queryKey: ["mf-catalogue", submitted, tag],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => fetchFundCatalogue(pageParam, submitted, tag),
    getNextPageParam: (last) => last.next_offset ?? undefined,
    retry: false,
    staleTime: 60 * 1000,
  });

  useEffect(() => {
    const node = sentinel.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && catalogue.hasNextPage && !catalogue.isFetchingNextPage) {
        void catalogue.fetchNextPage();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [catalogue]);

  const first = catalogue.data?.pages[0];
  const schemes = (catalogue.data?.pages ?? []).flatMap((page) => page.items);

  return (
    <section className="card flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-(--border-subtle) px-4 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-bold text-(--text-primary)">Mutual fund catalogue</h2>
          {first && (
            <p className="num-tabular text-xs text-(--text-secondary)">
              {first.total.toLocaleString("en-IN")} schemes
            </p>
          )}
        </div>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(query.trim());
          }}
        >
          <div className="flex flex-1 items-center gap-2 rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3 focus-within:border-(--section-sip)">
            <Search className="h-4 w-4 text-(--text-muted)" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a fund or scheme code"
              className="w-full bg-transparent py-2 text-sm outline-none"
            />
          </div>
          <button type="submit" className="rounded-xl bg-(--section-sip) px-3 text-sm font-semibold text-white">
            Search
          </button>
        </form>
        {first && (first.categories?.length ?? 0) > 0 && (
          <div className="mt-2.5 flex gap-1.5 overflow-x-auto pb-0.5">
            <button
              type="button"
              onClick={() => setTag("")}
              className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${tag === "" ? "bg-(--section-sip) text-white" : "bg-(--surface-3) text-(--text-secondary)"}`}
            >
              All
            </button>
            {first.categories.map((item) => (
              <button
                key={item.name}
                type="button"
                onClick={() => setTag(item.name)}
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${tag === item.name ? "bg-(--section-sip) text-white" : CATEGORY_TONE[item.name] ?? CATEGORY_TONE.Other}`}
              >
                {item.name}
                <span className="ml-1 num-tabular opacity-80">{item.count.toLocaleString("en-IN")}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {catalogue.isLoading && <p className="px-4 py-6 text-sm text-(--text-secondary)">Loading the live catalogue…</p>}
        {catalogue.isError && (
          <p className="px-4 py-6 text-sm text-(--bear-red)">
            {catalogue.error instanceof Error ? catalogue.error.message : "Catalogue unavailable."}
          </p>
        )}
        {!catalogue.isLoading && schemes.length === 0 && !catalogue.isError && (
          <p className="px-4 py-6 text-sm text-(--text-secondary)">No schemes match this search.</p>
        )}
        <ul>
          {schemes.map((scheme) => (
            <li key={scheme.scheme_code} className="flex items-center justify-between gap-3 border-b border-(--border-subtle) px-4 py-2.5">
              <p className="min-w-0 text-sm font-medium text-(--text-primary)">{scheme.scheme_name}</p>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${CATEGORY_TONE[scheme.category || "Other"] ?? CATEGORY_TONE.Other}`}>
                {scheme.category || "Other"}
              </span>
            </li>
          ))}
        </ul>
        <div ref={sentinel} className="py-3 text-center text-[11px] text-(--text-muted)">
          {catalogue.isFetchingNextPage ? "Loading more schemes…" : ""}
        </div>
      </div>
    </section>
  );
}
