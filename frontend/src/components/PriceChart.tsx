"use client";

import { useMemo, useState } from "react";
import { Candle } from "@/lib/types";

function rupee(value: number) {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: value >= 1000 ? 0 : 2 })}`;
}

function dateLabel(ts: number) {
  return new Date(ts * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "2-digit" });
}

export function PriceChart({ candles }: { candles: Candle[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const layout = useMemo(() => {
    const closes = candles.map((candle) => candle.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const width = 720;
    const height = 280;
    const left = 72;
    const right = 16;
    const top = 16;
    const bottom = 28;
    const innerW = width - left - right;
    const innerH = height - top - bottom;
    const points = closes.map((close, index) => {
      const x = left + (index / Math.max(closes.length - 1, 1)) * innerW;
      const y = top + (1 - (close - min) / span) * innerH;
      return { x, y, close, ts: candles[index].ts };
    });
    const ticks = [max, min + span / 2, min];
    return { width, height, left, top, bottom, innerH, points, ticks, min, max };
  }, [candles]);

  if (candles.length < 2) {
    return <p className="text-sm text-(--text-secondary)">Not enough prices for this range.</p>;
  }

  const active = hover == null ? layout.points[layout.points.length - 1] : layout.points[hover];
  const up = layout.points[layout.points.length - 1].close >= layout.points[0].close;
  const stroke = up ? "#0e9f6e" : "#e5484d";
  const gradientId = up ? "price-fill-up" : "price-fill-down";
  const line = layout.points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area = `${layout.left},${layout.top + layout.innerH} ${line} ${layout.points[layout.points.length - 1].x.toFixed(1)},${(layout.top + layout.innerH).toFixed(1)}`;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="h-64 w-full"
        role="img"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const x = ((event.clientX - rect.left) / rect.width) * layout.width;
          let nearest = 0;
          let best = Number.POSITIVE_INFINITY;
          layout.points.forEach((point, index) => {
            const distance = Math.abs(point.x - x);
            if (distance < best) {
              best = distance;
              nearest = index;
            }
          });
          setHover(nearest);
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.22} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        {layout.ticks.map((tick) => {
          const y = layout.top + (1 - (tick - layout.min) / (layout.max - layout.min || 1)) * layout.innerH;
          return (
            <g key={tick}>
              <line x1={layout.left} x2={layout.width - 16} y1={y} y2={y} stroke="#e7eaf3" strokeDasharray="4 4" />
              <text x={8} y={y + 4} fill="#94a0b8" fontSize="12">
                {rupee(tick)}
              </text>
            </g>
          );
        })}
        {hover != null && (
          <line x1={active.x} x2={active.x} y1={layout.top} y2={layout.top + layout.innerH} stroke="#d9deeb" strokeWidth="1" />
        )}
        <polygon points={area} fill={`url(#${gradientId})`} stroke="none" />
        <polyline fill="none" stroke={stroke} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" points={line} />
        <circle cx={active.x} cy={active.y} r="5" fill="#ffffff" stroke={stroke} strokeWidth="2.5" />
        <text x={layout.left} y={layout.height - 8} fill="#94a0b8" fontSize="12">
          {dateLabel(layout.points[0].ts)}
        </text>
        <text x={layout.width - 110} y={layout.height - 8} fill="#94a0b8" fontSize="12">
          {dateLabel(layout.points[layout.points.length - 1].ts)}
        </text>
      </svg>
      <div className="absolute right-3 top-3 rounded-md border border-(--border-subtle) bg-(--surface-1)/90 px-3 py-2 text-right shadow-(--shadow-card) backdrop-blur-sm">
        <div className="text-[11px] text-(--text-secondary)">{dateLabel(active.ts)}</div>
        <div className="num-tabular text-sm font-semibold text-(--text-primary)">{rupee(active.close)}</div>
      </div>
    </div>
  );
}
