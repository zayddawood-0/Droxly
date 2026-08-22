import { apiFetch } from "@/lib/api/client";

/** One function per documented endpoint in specs/api.md §7 (/comparisons). */

export type ComparisonStatus = "processing" | "completed" | "failed";
export type ChangeType = "factual" | "numeric" | "wording";
export type AlignmentQuality = "high" | "medium" | "low";

export type ComparisonSegment = {
  document: "a" | "b";
  page_number: number | null;
  excerpt: string;
};

export type ComparisonModification = {
  change_type: ChangeType;
  a_page_number: number | null;
  a_excerpt: string;
  b_page_number: number | null;
  b_excerpt: string;
  explanation: string;
};

export type ComparisonResult = {
  alignment_quality: AlignmentQuality;
  message: string | null;
  additions: ComparisonSegment[];
  deletions: ComparisonSegment[];
  modifications: ComparisonModification[];
};

export type ComparisonSummary = {
  id: string;
  document_a_id: string;
  document_b_id: string;
  status: ComparisonStatus;
  created_at: string;
};

export type ComparisonDetail = ComparisonSummary & {
  result: ComparisonResult | null;
};

export type PaginatedComparisons = {
  items: ComparisonSummary[];
  total: number;
  limit: number;
  offset: number;
};

/** FR-COMP-001 */
export function createComparison(input: { document_a_id: string; document_b_id: string }) {
  return apiFetch<{ id: string; status: "processing" }>("/comparisons", {
    method: "POST",
    body: input,
  });
}

/** FR-COMP-002, FR-COMP-003 */
export function getComparison(id: string) {
  return apiFetch<ComparisonDetail>(`/comparisons/${id}`);
}

/** FR-COMP-002 — this user's comparison history. */
export function listComparisons(params: { limit?: number; offset?: number } = {}) {
  return apiFetch<PaginatedComparisons>("/comparisons", { searchParams: params });
}
