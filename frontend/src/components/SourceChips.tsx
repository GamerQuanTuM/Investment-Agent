import { EvidenceItem } from "@/lib/types";

function formatDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** One chip per source: where a figure came from and the date the data is as of. */
export function SourceChips({ sources }: { sources: EvidenceItem[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Sources">
      {sources.map((source, index) => {
        const date = formatDate(source.data_date);
        const label = (
          <>
            <span className="font-semibold">{source.source_name}</span>
            {date ? <span className="text-(--text-muted)"> · as of {date}</span> : null}
          </>
        );
        const className =
          "rounded-full border border-(--border-subtle) bg-(--surface-2) px-2 py-0.5 text-[10px] text-(--text-secondary)";
        return source.source_url ? (
          <a
            key={`${source.source_name}-${index}`}
            href={source.source_url}
            target="_blank"
            rel="noreferrer"
            title={source.claim}
            className={`${className} hover:bg-(--surface-3)`}
          >
            {label}
          </a>
        ) : (
          <span key={`${source.source_name}-${index}`} title={source.claim} className={className}>
            {label}
          </span>
        );
      })}
    </div>
  );
}
