import Link from "next/link";

const COLUMNS = [
  {
    heading: "Product",
    links: [
      { label: "Dashboard", href: "/" },
      { label: "Stocks", href: "/stocks" },
      { label: "SIP planner", href: "/sip" },
      { label: "Ask AI", href: "/chat" },
    ],
  },
  {
    heading: "Data sources",
    links: [
      { label: "NSE live quotes", href: "/stocks" },
      { label: "BSE live quotes", href: "/stocks" },
      { label: "AMFI mutual fund NAVs", href: "/sip" },
      { label: "INDmoney broker vault", href: "/" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "Not investment advice", href: "#" },
      { label: "Privacy policy", href: "#" },
      { label: "Terms of use", href: "#" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="mt-auto border-t border-(--border-subtle) bg-(--surface-1)">
      <div className="mx-auto max-w-7xl px-4 py-6 lg:px-8">
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          <div className="col-span-2 sm:col-span-1">
            <Link href="/" className="flex items-center gap-2">
              <span className="icon-badge h-8 w-8 bg-(--section-gold-soft) text-base font-bold text-(--section-gold)">₹</span>
              <span className="text-sm font-bold tracking-tight text-(--text-primary)">MudraLens</span>
            </Link>
            <p className="mt-3 max-w-55 text-xs leading-relaxed text-(--text-secondary)">
              Evidence-grounded Indian equity &amp; mutual fund research, with disciplined 3–5 year portfolio guidance.
            </p>
          </div>
          {COLUMNS.map((col) => (
            <div key={col.heading}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-(--text-muted)">{col.heading}</h3>
              <ul className="mt-3 space-y-2">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <Link href={link.href} className="text-xs text-(--text-secondary) transition-colors hover:text-(--text-primary)">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-8 flex flex-col gap-2 border-t border-(--border-subtle) pt-5 text-[11px] text-(--text-muted) sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} MudraLens. Research output only — not a solicitation to buy or sell securities.</p>
          <p>NSE · BSE · AMFI data via INDstocks</p>
        </div>
      </div>
    </footer>
  );
}
