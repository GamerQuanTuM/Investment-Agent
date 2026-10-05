"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Styled Markdown for chat bubbles: bullets, numbered lists, bold, italics, tables, quotes. */
const components: Components = {
  p: ({ children }) => <p className="my-1.5 whitespace-pre-line first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-(--text-primary)">{children}</strong>,
  em: ({ children }) => <em className="italic text-(--text-secondary)">{children}</em>,
  ul: ({ children }) => <ul className="my-1.5 list-disc space-y-1 pl-5 marker:text-(--section-chat)">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 list-decimal space-y-1 pl-5 marker:font-semibold">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  h1: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-bold text-(--text-primary)">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-bold text-(--text-primary)">{children}</h3>,
  h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-bold text-(--text-primary) first:mt-0">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 rounded-r-lg border-l-4 border-(--section-chat) bg-(--section-chat-soft) px-3 py-1.5 text-xs">
      {children}
    </blockquote>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="font-medium text-(--section-chat) underline">
      {children}
    </a>
  ),
  code: ({ children }) => <code className="rounded bg-(--surface-3) px-1 py-0.5 text-[0.85em]">{children}</code>,
  hr: () => <hr className="my-2 border-(--border-subtle)" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-(--border-subtle)">
      <table className="w-full min-w-[22rem] border-collapse text-left text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-(--surface-2)">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-(--border-subtle) px-2.5 py-1.5 text-[11px] font-bold uppercase tracking-wide text-(--text-primary)">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-t border-(--border-subtle) px-2.5 py-1.5 align-top leading-relaxed">{children}</td>
  ),
};

export function RichText({ text }: { text: string }) {
  return (
    <div className="rich-text whitespace-normal">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
