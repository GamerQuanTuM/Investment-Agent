"use client";

function toneFor(score: number): { stroke: string; text: string } {
  if (score >= 70) return { stroke: "var(--bull-green)", text: "text-(--bull-green)" };
  if (score >= 40) return { stroke: "var(--section-gold)", text: "text-(--section-gold)" };
  return { stroke: "var(--bear-red)", text: "text-(--bear-red)" };
}

export function ScoreRing({ label, score, size = 88 }: { label: string; score: number | null; size?: number }) {
  const radius = size / 2 - 7;
  const circumference = 2 * Math.PI * radius;
  const clamped = score == null ? 0 : Math.max(0, Math.min(100, score));
  const offset = circumference * (1 - clamped / 100);
  const tone = score == null ? { stroke: "var(--border-medium)", text: "text-(--text-muted)" } : toneFor(clamped);

  return (
    <div className="card-row flex flex-col items-center gap-2 p-4">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-3)" strokeWidth={7} />
          {score != null && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={tone.stroke}
              strokeWidth={7}
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`num-tabular text-lg font-bold ${tone.text}`}>{score == null ? "—" : Math.round(score)}</span>
        </div>
      </div>
      <span className="text-xs font-semibold text-(--text-secondary)">{label}</span>
    </div>
  );
}
