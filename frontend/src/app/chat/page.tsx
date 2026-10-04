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
import { GuidanceNote } from "@/lib/types";

type Collected = {
  intent: "stock" | "sip" | null;
  symbol: string | null;
  horizon_years: number | null;
  monthly_amount: number | null;
  risk: string | null;
};

type Plan = {
  style: string;
  horizon_years: number;
  monthly_amount: number;
  note: string;
  sleeves: { symbol: string; label: string; weight_pct: number; monthly_inr: number }[];
};

type Bubble = {
  role: "user" | "agent";
  text: string;
  time: string;
  guidance?: GuidanceNote;
  plan?: Plan;
};

const EMPTY_COLLECTED: Collected = { intent: null, symbol: null, horizon_years: null, monthly_amount: null, risk: null };

const SUGGESTIONS = [
  "Should I buy TCS for 5 years?",
  "Build me a ₹10,000 SIP for 10 years, flexi cap",
  "Is RELIANCE good for a 3 year hold?",
  "I want a small cap SIP of ₹5,000 for 7 years",
];

const stanceTone: Record<GuidanceNote["stance"], string> = {
  CONSIDER: "text-(--bull-green) bg-(--bull-green-soft)",
  WAIT: "text-(--section-gold) bg-(--section-gold-soft)",
  AVOID: "text-(--bear-red) bg-(--bear-red-soft)",
};

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function freshGreeting(): Bubble {
  return {
    role: "agent",
    text: "Ask about a stock or a SIP. I will ask for the holding span, monthly amount, and cap style before I answer.",
    time: timestamp(),
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
  return (
    <div className="mt-2 space-y-1.5 rounded-xl border border-(--border-subtle) bg-(--surface-1) p-3">
      {plan.sleeves.map((row) => (
        <div key={row.symbol} className="flex items-center justify-between text-xs">
          <span className="font-semibold text-(--text-primary)">{row.label}</span>
          <span className="num-tabular font-semibold text-(--section-sip)">₹{row.monthly_inr.toLocaleString("en-IN")} · {row.weight_pct}%</span>
        </div>
      ))}
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

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState<Bubble[]>([freshGreeting()]);
  const [collected, setCollected] = useState<Collected>(EMPTY_COLLECTED);
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
        { role: "agent", text: reply.text, time: timestamp(), guidance: reply.guidance, plan: reply.plan },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        { role: "agent", text: err instanceof Error ? err.message : "The agent could not answer.", time: timestamp() },
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
    setSessionId(crypto.randomUUID());
    setMessages([freshGreeting()]);
    setCollected(EMPTY_COLLECTED);
    setInput("");
  };

  return (
    <main className="mx-auto flex min-h-[calc(100vh-7.5rem)] max-w-3xl flex-col px-4 py-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge h-9 w-9 bg-(--section-chat-soft) text-(--section-chat)">
            <Sparkles className="h-4.5 w-4.5" />
          </span>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-(--text-primary)">Ask the agent</h1>
            <p className="text-sm text-(--text-secondary)">It keeps asking until it has the facts it needs. It does not place orders.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={reset}
          className="flex shrink-0 items-center gap-1.5 rounded-full border border-(--border-subtle) bg-(--surface-1) px-3 py-1.5 text-xs font-semibold text-(--text-secondary) transition-colors hover:bg-(--surface-2)"
        >
          <RotateCcw className="h-3.5 w-3.5" /> New chat
        </button>
      </div>

      {/* Collected facts tracker */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        <FactChip icon={Target} label="Intent" value={collected.intent} />
        <FactChip icon={Tag} label="Symbol" value={collected.symbol} />
        <FactChip icon={CalendarClock} label="Horizon" value={collected.horizon_years ? `${collected.horizon_years}y` : null} />
        <FactChip icon={Wallet} label="Monthly" value={collected.monthly_amount ? `₹${collected.monthly_amount.toLocaleString("en-IN")}` : null} />
        <FactChip icon={Gauge} label="Style" value={collected.risk} />
      </div>

      {/* Chat panel */}
      <div className="mt-4 flex flex-1 flex-col overflow-hidden rounded-2xl border border-(--border-subtle) bg-(--surface-1) shadow-(--shadow-card)">
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
          {messages.map((message, index) => {
            const isAgent = message.role === "agent";
            return (
              <div key={`${message.role}-${index}`} className={`flex items-end gap-2 ${isAgent ? "" : "flex-row-reverse"}`}>
                <span
                  className={`icon-badge h-7 w-7 shrink-0 ${
                    isAgent ? "bg-(--section-chat-soft) text-(--section-chat)" : "bg-(--section-portfolio-soft) text-(--section-portfolio)"
                  }`}
                >
                  {isAgent ? <Bot className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                </span>
                <div className={`flex max-w-[78%] flex-col ${isAgent ? "items-start" : "items-end"}`}>
                  <div
                    className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-line ${
                      isAgent ? "card-row text-(--text-primary)" : "bg-(--section-chat) text-white"
                    }`}
                  >
                    {message.text}
                    {message.guidance && <GuidanceCard guidance={message.guidance} />}
                    {message.plan && <PlanCard plan={message.plan} />}
                  </div>
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

        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-1.5 border-t border-(--border-subtle) p-3">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => void send(suggestion)}
                className="nav-pill border border-(--border-subtle) bg-(--surface-2) px-3 py-1.5 text-xs text-(--text-secondary) transition-colors hover:bg-(--surface-3) hover:text-(--text-primary)"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={submit} className="flex items-center gap-2 border-t border-(--border-subtle) p-3">
          <label className="sr-only" htmlFor="chat-input">Message the agent</label>
          <input
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Should I buy TCS for 5 years?"
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
