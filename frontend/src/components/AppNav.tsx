"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useState, FormEvent } from "react";
import { LayoutDashboard, CandlestickChart, Sparkles, PiggyBank, FlaskConical, Search, Bell } from "lucide-react";

const LINKS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, color: "var(--section-portfolio)", soft: "var(--section-portfolio-soft)" },
  { href: "/stocks", label: "Stocks", icon: CandlestickChart, color: "var(--section-stocks)", soft: "var(--section-stocks-soft)" },
  { href: "/research", label: "Research", icon: FlaskConical, color: "var(--section-research)", soft: "var(--section-research-soft)" },
  { href: "/chat", label: "Ask AI", icon: Sparkles, color: "var(--section-chat)", soft: "var(--section-chat-soft)" },
  { href: "/sip", label: "SIP", icon: PiggyBank, color: "var(--section-sip)", soft: "var(--section-sip-soft)" },
];

export function AppNav() {
  const path = usePathname();
  const router = useRouter();
  const [query, setQuery] = useState("");

  const onSearch = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    router.push(`/stocks/${encodeURIComponent(trimmed.toUpperCase())}`);
  };

  return (
    <header className="sticky top-0 z-40 border-b border-(--border-subtle) bg-white/90 backdrop-blur-md">
      {/* Row 1: brand, global search, profile */}
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 lg:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span className="icon-badge h-8 w-8 bg-(--section-gold-soft) text-base font-bold text-(--section-gold)">₹</span>
          <span className="hidden text-sm font-bold tracking-tight text-(--text-primary) sm:inline">MudraLens</span>
        </Link>

        <form onSubmit={onSearch} className="relative flex-1 max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-(--text-muted)" />
          <label htmlFor="global-search" className="sr-only">Search a stock symbol</label>
          <input
            id="global-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search RELIANCE, TCS, INFY…"
            className="w-full rounded-full border border-(--border-subtle) bg-(--surface-2) py-2 pl-9 pr-3 text-sm text-(--text-primary) outline-none transition-colors focus:border-(--section-stocks) focus:bg-white focus:ring-2 focus:ring-(--section-stocks)/25"
          />
        </form>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <button
            type="button"
            aria-label="Notifications"
            className="hidden h-9 w-9 items-center justify-center rounded-full border border-(--border-subtle) bg-(--surface-2) text-(--text-secondary) transition-colors hover:bg-(--surface-3) sm:flex"
          >
            <Bell className="h-4 w-4" />
          </button>
          <span className="icon-badge h-9 w-9 bg-(--section-portfolio-soft) text-sm font-bold text-(--section-portfolio)" title="Investor profile">
            IN
          </span>
        </div>
      </div>

      {/* Row 2: section nav */}
      <div className="mx-auto flex max-w-7xl items-center gap-1.5 overflow-x-auto px-4 pb-2.5 lg:px-8">
        {LINKS.map((link) => {
          const active = path === link.href;
          const Icon = link.icon;
          return (
            <Link
              key={link.href}
              href={link.href}
              style={active ? { backgroundColor: link.soft, color: link.color } : undefined}
              className={`nav-pill flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold ${
                active ? "" : "text-(--text-secondary) hover:bg-(--surface-3) hover:text-(--text-primary)"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {link.label}
            </Link>
          );
        })}
      </div>
    </header>
  );
}
