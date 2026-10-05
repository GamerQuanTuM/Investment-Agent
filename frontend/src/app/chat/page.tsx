"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Sparkles,
  Bot,
  User,
  RotateCcw,
  Target,
  Tag,
  CalendarClock,
  Wallet,
  Gauge,
  Check,
  Send,
} from "lucide-react";
import { sendChat } from "@/lib/api";
import { ChatCollected, ChatComparison, ChatReply, EvidenceItem, GlossaryEntry, GuidanceNote, StockPlan } from "@/lib/types";
import { DataUnavailableTile, StockPlanCard } from "@/components/StockPlanCard";
import { ComparisonCard } from "@/components/ComparisonCard";
import { GlossaryCard } from "@/components/GlossaryCard";
import { SourceChips } from "@/components/SourceChips";

type Plan = NonNullable<ChatReply["plan"]>;

type Bubble = {
  role: "user" | "agent";
  text: string;
  time: string;
  guidance?: GuidanceNote;
  plan?: Plan;
  stockPlan?: StockPlan;
  glossary?: GlossaryEntry;
  comparison?: ChatComparison;
  sources?: EvidenceItem[];
  suggestions?: string[];
  dataUnavailable?: boolean;
  isError?: boolean;
};

const EMPTY_COLLECTED: ChatCollected = {
  intent: null,
  symbol: null,
  horizon_years: null,
  monthly_amount: null,
  amount_inr: null,
  amount_kind: null,
  risk: null,
  stock_count: null,
  experience_level: null,
};

const STARTERS = [
  "I'm new, where do I start?",
  "Suggest 10 stocks for ₹10,000",
  "What is an ETF?",
  "Plan a ₹5,000 monthly SIP",
];

const INTENT_LABELS: Record<string, string> = {
  education: "Learning",
  stock_list: "Stock list",
  stock_single: "One stock",
  plan_sip_fund: "Fund SIP",
  plan_sip_etf: "ETF SIP",
  fund_list: "Fund list",
  market_overview: "Market check",
  portfolio_help: "My portfolio",
};

const stanceTone: Record<GuidanceNote["stance"], string> = {
  CONSIDER: "text-(--bull-green) bg-(--bull-green-soft)",
  WAIT: "text-(--section-gold) bg-(--section-gold-soft)",
  AVOID: "text-(--bear-red) bg-(--bear-red-soft)",
};

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** The card already shows the rows, totals, reality check and disclaimer, so the bubble keeps
 * only the intro and the beginner tips from the plain-text reply. */
function textBesideStockPlan(text: string) {
  const parts = text.split("\n\n");
  return [parts[0], ...parts.slice(3)]
    .filter((part) => !part.startsWith("Reality check") && !part.startsWith("Educational guidance"))
    .join("\n\n");
}

function freshGreeting(): Bubble {
  return {
    role: "agent",
    text:
      "Hi! Ask me about a stock, a mutual fund or SIP, or what any investing word means. " +
      "No experience needed: I'll explain as we go, and you can say \"not sure\" to any question.",
    time: timestamp(),
    suggestions: STARTERS,
  };
}

function GuidanceCard({ guidance }: { guidance: GuidanceNote }) {
  return (
    <div className="mt-2 rounded-xl border border-(--border-subtle) bg-(--surface-1) p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold text-(--text-primary)">{guidance.symbol}</span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${stanceTone[guidance.stance]}`}>{guidance.stance}</span>
      </div>
      {guidance.live_price != null && (
        <p className="num-tabular mt-1 text-xs text-(--text-secondary)">
          Live ₹{guidance.live_price.toLocaleString("en-IN")}
          {guidance.pe_ratio != null ? ` · P/E ${guidance.pe_ratio}` : ""}
        </p>
      )}
    </div>
  );
}

function PlanCard({ plan }: { plan: Plan }) {
  const lump = plan.kind === "lump_sum";
  return (
    <div className="mt-2 space-y-1.5 rounded-xl border border-(--border-subtle) bg-(--surface-1) p-3">
      {plan.title && (
        <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-(--text-muted)">{plan.title}</p>
      )}
      {plan.sleeves.map((row, index) => {
        const rupees = lump ? row.amount_inr : row.monthly_inr;
        const returns = [
          row.return_3y_pct != null ? `3y ${row.return_3y_pct}%/yr` : null,
          row.return_5y_pct != null ? `5y ${row.return_5y_pct}%/yr` : null,
        ].filter(Boolean);
        return (
          <div key={`${row.symbol}-${index}`} className="flex items-start justify-between gap-3 text-xs">
            <span className="min-w-0">
              <span className="font-semibold text-(--text-primary)">{row.label}</span>
              {returns.length > 0 && <span className="block text-[11px] text-(--text-muted)">{returns.join(" · ")}</span>}
            </span>
            <span className="num-tabular shrink-0 font-semibold text-(--section-sip)">
              {rupees != null ? `₹${rupees.toLocaleString("en-IN")}` : "—"} · {row.weight_pct}%
            </span>
          </div>
        );
      })}
      {plan.spread_option && (
        <p className="border-t border-(--border-subtle) pt-1.5 text-[11px] text-(--text-secondary)">
          Or spread over {plan.spread_option.months} months: about ₹
          {Math.round(plan.spread_option.monthly_inr).toLocaleString("en-IN")} a month.
        </p>
      )}
    </div>
  );
}

function FactChip({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number | null;
}) {
  const filled = value != null && value !== "";
  return (
    <div
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        filled
          ? "border-(--bull-green)/30 bg-(--bull-green-soft) text-(--bull-green)"
          : "border-(--border-subtle) bg-(--surface-2) text-(--text-muted)"
      }`}
    >
      {filled ? <Check className="h-3 w-3" /> : <Icon className="h-3 w-3" />}
      <span>{label}{filled ? `: ${value}` : ""}</span>
    </div>
  );
}

function Chips({ items, onPick, disabled }: { items: string[]; onPick: (text: string) => void; disabled: boolean }) {
  if (!items.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((item) => (
        <button
          key={item}
          type="button"
          disabled={disabled}
          onClick={() => onPick(item)}
          className="nav-pill border border-(--border-subtle) bg-(--surface-1) px-3 py-1.5 text-xs text-(--section-chat) transition-colors hover:bg-(--section-chat-soft) disabled:cursor-not-allowed disabled:opacity-60"
        >
          {item}
        </button>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState<Bubble[]>([freshGreeting()]);
  const [collected, setCollected] = useState<ChatCollected>(EMPTY_COLLECTED);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setInput("");
    setMessages((current) => [...current, { role: "user", text, time: timestamp() }]);
    setBusy(true);
    try {
      const reply = await sendChat(sessionId, text);
      setCollected(reply.collected);
      setMessages((current) => [
        ...current,
        {
          role: "agent",
          text: reply.text,
          time: timestamp(),
          guidance: reply.guidance,
          plan: reply.plan,
          stockPlan: reply.stock_plan ?? undefined,
          glossary: reply.glossary,
          comparison: reply.comparison,
          sources: reply.sources,
          suggestions: reply.suggestions,
          dataUnavailable: reply.data_status === "DATA_UNAVAILABLE",
          isError: reply.error,
        },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        { role: "agent", text: err instanceof Error ? err.message : "The agent could not answer.", time: timestamp(), isError: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  const reset = () => {
    // Clear the server-side session too, so "start over" really starts over.
    void sendChat(sessionId, "start over").catch(() => undefined);
    setSessionId(crypto.randomUUID());
    setMessages([freshGreeting()]);
    setCollected(EMPTY_COLLECTED);
    setInput("");
  };

  const amountLabel = collected.amount_inr
    ? `₹${collected.amount_inr.toLocaleString("en-IN")}${collected.amount_kind === "monthly" ? "/mo" : ""}`
    : null;
  const lastAgentIndex = messages.reduce((found, message, index) => (message.role === "agent" ? index : found), -1);

  return (
    <main className="mx-auto flex min-h-[calc(100vh-7.5rem)] max-w-3xl flex-col px-4 py-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-9 w-9 bg-(--section-chat-soft) text-(--section-chat)">
            <Sparkles className="h-4.5 w-4.5" />
          </span>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-(--text-primary)">Ask the agent</h1>
            <p className="text-sm text-(--text-secondary)">Guidance only. It does not place orders or promise returns.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={reset}
          className="flex shrink-0 items-center gap-1.5 rounded-full border border-(--border-subtle) bg-(--surface-1) px-3 py-1.5 text-xs font-semibold text-(--text-secondary) transition-colors hover:bg-(--surface-2)"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Start over
        </button>
      </div>

      {/* Collected facts tracker */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        <FactChip icon={Target} label="Topic" value={collected.intent ? (INTENT_LABELS[collected.intent] ?? collected.intent) : null} />
        <FactChip icon={Tag} label="Symbol" value={collected.symbol} />
        <FactChip icon={CalendarClock} label="Horizon" value={collected.horizon_years ? `${collected.horizon_years}y` : null} />
        <FactChip icon={Wallet} label="Amount" value={amountLabel} />
        <FactChip icon={Gauge} label="Risk comfort" value={collected.risk} />
      </div>

      {/* Chat panel */}
      <div className="mt-4 flex flex-1 flex-col overflow-hidden rounded-2xl border border-(--border-subtle) bg-(--surface-1) shadow-(--shadow-card)">
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
          {messages.map((message, index) => {
            const isAgent = message.role === "agent";
            const showText = !((message.glossary || message.comparison) && !message.isError);
            return (
              <div key={`${message.role}-${index}`} className={`flex items-end gap-2 ${isAgent ? "" : "flex-row-reverse"}`}>
                <span
                  className={`icon-badge h-7 w-7 shrink-0 ${
                    isAgent ? "bg-(--section-chat-soft) text-(--section-chat)" : "bg-(--section-portfolio-soft) text-(--section-portfolio)"
                  }`}
                >
                  {isAgent ? <Bot className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                </span>
                <div className={`flex min-w-0 max-w-[88%] flex-col ${isAgent ? "items-start" : "items-end"}`}>
                  <div
                    className={`max-w-full rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-line ${
                      message.isError
                        ? "border border-(--bear-red)/40 bg-(--bear-red-soft) text-(--bear-red)"
                        : isAgent
                          ? "card-row text-(--text-primary)"
                          : "bg-(--section-chat) text-white"
                    }`}
                  >
                    {message.dataUnavailable ? (
                      <DataUnavailableTile message={message.text} />
                    ) : (
                      <>
                        {showText && (message.stockPlan ? textBesideStockPlan(message.text) : message.text)}
                        {message.glossary && <GlossaryCard entry={message.glossary} />}
                        {message.comparison && <ComparisonCard comparison={message.comparison} />}
                      </>
                    )}
                    {message.stockPlan && (
                      <div className="mt-2 whitespace-normal">
                        <StockPlanCard plan={message.stockPlan} />
                      </div>
                    )}
                    {message.guidance && <GuidanceCard guidance={message.guidance} />}
                    {message.plan && <PlanCard plan={message.plan} />}
                    {message.sources && <SourceChips sources={message.sources} />}
                  </div>
                  {isAgent && message.suggestions && (
                    <Chips
                      items={message.suggestions}
                      onPick={(text) => void send(text)}
                      disabled={busy || index !== lastAgentIndex}
                    />
                  )}
                  <span className="mt-1 text-[10px] text-(--text-muted)">{message.time}</span>
                </div>
              </div>
            );
          })}
          {busy && (
            <div className="flex items-end gap-2">
              <span className="icon-badge h-7 w-7 shrink-0 bg-(--section-chat-soft) text-(--section-chat)">
                <Bot className="h-3.5 w-3.5" />
              </span>
              <div className="card-row flex max-w-[60%] items-center gap-1.5 px-3.5 py-2.5 text-sm text-(--text-secondary)">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-(--text-muted) [animation-delay:-0.2s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-(--text-muted) [animation-delay:-0.1s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-(--text-muted)" />
              </div>
            </div>
          )}
        </div>

        <form onSubmit={submit} className="flex items-center gap-2 border-t border-(--border-subtle) p-3">
          <label className="sr-only" htmlFor="chat-input">Message the agent</label>
          <input
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask anything, e.g. “Suggest 10 stocks for ₹10,000”"
            className="flex-1 rounded-xl border border-(--border-subtle) bg-(--surface-2) px-3.5 py-2.5 text-sm text-(--text-primary) outline-none transition-colors focus:border-(--section-chat) focus:bg-(--surface-1)"
          />
          <button
            type="submit"
            aria-label="Send message"
            className="flex items-center gap-1.5 rounded-xl bg-(--section-chat) px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={busy || !input.trim()}
          >
            <Send className="h-3.5 w-3.5" />
            Send
          </button>
        </form>
      </div>
    </main>
  );
}
