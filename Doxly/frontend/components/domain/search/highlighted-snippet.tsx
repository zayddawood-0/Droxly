import { Fragment } from "react";
import type { SearchSnippet } from "@/lib/api/search";

/**
 * ui-ux.md §12 — "snippet highlighting uses `<mark>` semantics, not
 * color-only spans." api.md §8 deliberately returns character offsets
 * rather than embedded markup: snippet text comes from an uploaded
 * document (untrusted input, security.md §6.2), so it is only ever
 * rendered as plain text — the `<mark>` wrapping happens here, in real
 * JSX, never via dangerouslySetInnerHTML.
 */
export function HighlightedSnippet({ snippet }: { snippet: SearchSnippet }) {
  const { text, highlights } = snippet;
  const ranges = [...highlights]
    .map((h) => ({ start: Math.max(0, h.start), end: Math.min(text.length, h.end) }))
    .filter((h) => h.start < h.end)
    .sort((a, b) => a.start - b.start);

  const parts: { text: string; marked: boolean }[] = [];
  let cursor = 0;
  for (const { start, end } of ranges) {
    if (start > cursor) parts.push({ text: text.slice(cursor, start), marked: false });
    parts.push({ text: text.slice(Math.max(start, cursor), end), marked: true });
    cursor = Math.max(cursor, end);
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), marked: false });

  return (
    <p className="text-sm text-muted-foreground">
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part.marked ? (
            <mark className="rounded-sm bg-primary/20 text-foreground">{part.text}</mark>
          ) : (
            part.text
          )}
        </Fragment>
      ))}
    </p>
  );
}
