import { apiFetch } from "@/lib/api/client";

/** One function per documented endpoint in specs/api.md §3 (/documents). */

export type DocumentStatus =
  | "queued"
  | "extracting"
  | "chunking"
  | "embedding"
  | "ready"
  | "failed";

export type DocumentTagRef = { id: string; name: string; color: string | null };

export type DocumentListItem = {
  id: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  status: DocumentStatus;
  page_count: number | null;
  tags: DocumentTagRef[];
  created_at: string;
  updated_at: string;
};

export type DocumentDetail = DocumentListItem & {
  checksum_sha256: string;
  processing_error: string | null;
  extracted_text_available: boolean;
};

export type PaginatedDocuments = {
  items: DocumentListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type DocumentListParams = {
  limit?: number;
  offset?: number;
  status?: DocumentStatus;
  tag_id?: string;
  mime_type?: string;
  sort?: "created_at_desc" | "created_at_asc" | "name_asc" | "size_desc";
};

/** FR-DOC-002 */
export function listDocuments(params: DocumentListParams = {}) {
  return apiFetch<PaginatedDocuments>("/documents", { searchParams: params });
}

/** FR-DOC-003 */
export function getDocument(id: string) {
  return apiFetch<DocumentDetail>(`/documents/${id}`);
}

/** FR-DOC-001, step 1 of 3 (specs/architecture.md §4) */
export function presignUpload(input: {
  file_name: string;
  mime_type: string;
  size_bytes: number;
}) {
  return apiFetch<{
    document_id: string;
    upload_url: string;
    upload_method: "PUT";
    upload_headers: Record<string, string>;
    expires_in: number;
  }>("/documents/presign", { method: "POST", body: input });
}

/** FR-DOC-001, step 3 — after the browser's direct PUT to storage. */
export function confirmUpload(documentId: string) {
  return apiFetch<{ id: string; status: "queued" }>(
    `/documents/${documentId}/confirm`,
    { method: "POST" },
  );
}

/** FR-DOC-004 (rename), FR-DOC-006 (tag assignment) */
export function updateDocument(
  id: string,
  input: { file_name?: string; tag_ids?: string[] },
) {
  return apiFetch<DocumentDetail>(`/documents/${id}`, {
    method: "PATCH",
    body: input,
  });
}

/** FR-DOC-005 */
export function deleteDocument(id: string) {
  return apiFetch<void>(`/documents/${id}`, { method: "DELETE" });
}

/** FR-DOC-003 — short-lived presigned GET to the original file. */
export function getDownloadUrl(id: string) {
  return apiFetch<{ download_url: string; expires_in: number }>(
    `/documents/${id}/download`,
  );
}

/** FR-DOC-008 — cheap poll fallback; SSE variant lands with Phase 5's live status UI. */
export function getDocumentStatus(id: string) {
  return apiFetch<{ status: DocumentStatus; processing_error: string | null }>(
    `/documents/${id}/status`,
  );
}
