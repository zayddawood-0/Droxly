import { apiFetch } from "@/lib/api/client";

/** One function per documented endpoint in specs/api.md §5 (/summaries). */

export type SummaryType = "brief" | "detailed" | "bullet_points";
export type SummaryStatus = "processing" | "completed" | "failed";

export type SummaryListItem = {
  id: string;
  summary_type: SummaryType;
  status: SummaryStatus;
  created_at: string;
};

export type SummaryDetail = {
  id: string;
  document_id: string;
  summary_type: SummaryType;
  status: SummaryStatus;
  content: string | null;
  created_at: string;
};

export type PaginatedSummaries = {
  items: SummaryListItem[];
  total: number;
  limit: number;
  offset: number;
};

/** FR-SUM-001 — enqueues the background Summarization workflow; response status is always "processing". */
export function createSummary(documentId: string, summaryType: SummaryType) {
  return apiFetch<{ id: string; document_id: string; summary_type: SummaryType; status: "processing" }>(
    `/documents/${documentId}/summaries`,
    { method: "POST", body: { summary_type: summaryType } },
  );
}

/** FR-SUM-002 — every summary ever generated for this document, newest first; regenerating never overwrites a prior one. */
export function listSummaries(documentId: string, params: { limit?: number; offset?: number } = {}) {
  return apiFetch<PaginatedSummaries>(`/documents/${documentId}/summaries`, { searchParams: params });
}

/** FR-SUM-001, FR-SUM-002 — `content` is null while `status="processing"`; the client polls this until it isn't. */
export function getSummary(id: string) {
  return apiFetch<SummaryDetail>(`/summaries/${id}`);
}
