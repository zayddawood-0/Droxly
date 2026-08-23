import { apiFetch } from "@/lib/api/client";
import type { DocumentStatus } from "@/lib/api/documents";

/** One function per documented endpoint in specs/api.md §8 (/search). */

export type SearchSnippet = {
  text: string;
  highlights: { start: number; end: number }[];
};

export type SearchResultRow = {
  document_id: string;
  file_name: string;
  snippet: SearchSnippet;
  relevance_score: number;
  matched_page: number | null;
};

export type PaginatedSearchResults = {
  items: SearchResultRow[];
  total: number;
  limit: number;
  offset: number;
};

export type SearchParams = {
  q: string;
  limit?: number;
  offset?: number;
  mime_type?: string;
  tag_id?: string;
  status?: DocumentStatus;
  date_from?: string;
  date_to?: string;
};

/** FR-SEARCH-001/002/003 */
export function search(params: SearchParams) {
  return apiFetch<PaginatedSearchResults>("/search", { searchParams: params });
}
