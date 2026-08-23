import Link from "next/link";
import { FileText } from "lucide-react";

import { HighlightedSnippet } from "@/components/domain/search/highlighted-snippet";
import type { SearchResultRow } from "@/lib/api/search";

export type GroupedResult = {
  document_id: string;
  file_name: string;
  matches: { snippet: SearchResultRow["snippet"]; matched_page: number | null }[];
};

/** api.md §8 — one row per matching chunk; rows sharing a document_id are grouped into one card. */
export function groupResultsByDocument(rows: SearchResultRow[]): GroupedResult[] {
  const byDocument = new Map<string, GroupedResult>();
  for (const row of rows) {
    const existing = byDocument.get(row.document_id);
    if (existing) {
      existing.matches.push({ snippet: row.snippet, matched_page: row.matched_page });
    } else {
      byDocument.set(row.document_id, {
        document_id: row.document_id,
        file_name: row.file_name,
        matches: [{ snippet: row.snippet, matched_page: row.matched_page }],
      });
    }
  }
  return [...byDocument.values()];
}

/**
 * ui-ux.md §12 — "document-level cards with highlighted matching snippets,
 * potentially multiple snippets per document"; "clicking a result opens the
 * Document Viewer scrolled/highlighted to the matching location."
 */
export function ResultCard({ result }: { result: GroupedResult }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <div className="flex items-center gap-2">
        <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="truncate text-sm font-medium">{result.file_name}</span>
      </div>
      <div className="flex flex-col gap-2">
        {result.matches.map((match, i) => (
          <Link
            key={i}
            href={`/documents/${result.document_id}${match.matched_page ? `?page=${match.matched_page}` : ""}`}
            className="flex flex-col gap-1 rounded-md border border-transparent px-2 py-1.5 outline-none transition-colors hover:border-border hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <HighlightedSnippet snippet={match.snippet} />
            {match.matched_page && (
              <span className="text-xs text-muted-foreground">Page {match.matched_page}</span>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
