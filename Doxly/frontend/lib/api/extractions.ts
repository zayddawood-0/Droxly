import { apiFetch } from "@/lib/api/client";

/** One function per documented endpoint in specs/api.md §6 (/extractions). */

export type ExtractionStatus = "processing" | "completed" | "failed";
export type FieldType = "string" | "number" | "date" | "boolean";

export type TemplateField = {
  name: string;
  type: FieldType;
  description: string;
  required: boolean;
};

export type ExtractionTemplate = {
  key: string;
  name: string;
  description: string;
  fields: TemplateField[];
};

export type SchemaField = {
  name: string;
  type: FieldType;
  description?: string;
  required: boolean;
};

export type ExtractionResultField = {
  field: string;
  value: unknown;
  confidence: number | null;
  not_found_reason: string | null;
  corrected: boolean;
  citation: { page_number: number | null; snippet: string } | null;
};

export type ExtractionSummary = {
  id: string;
  template_key: string | null;
  status: ExtractionStatus;
  created_at: string;
};

export type ExtractionDetail = {
  id: string;
  document_id: string;
  template_key: string | null;
  schema: SchemaField[];
  status: ExtractionStatus;
  result: ExtractionResultField[];
  created_at: string;
};

export type PaginatedExtractions = {
  items: ExtractionSummary[];
  total: number;
  limit: number;
  offset: number;
};

/** FR-EXT-002 — preset schemas so users aren't required to hand-define one. */
export function listExtractionTemplates() {
  return apiFetch<{ items: ExtractionTemplate[] }>("/extractions/templates");
}

/** FR-EXT-001 — exactly one of templateKey/schema must be provided. */
export function createExtraction(input: {
  document_id: string;
  template_key?: string;
  schema?: SchemaField[];
}) {
  return apiFetch<{ id: string; status: "processing" }>("/extractions", {
    method: "POST",
    body: input,
  });
}

/** FR-EXT-001, FR-EXT-003 */
export function getExtraction(id: string) {
  return apiFetch<ExtractionDetail>(`/extractions/${id}`);
}

/** FR-EXT-001 — extraction history for a document. */
export function listExtractionsForDocument(
  documentId: string,
  params: { limit?: number; offset?: number } = {},
) {
  return apiFetch<PaginatedExtractions>(`/documents/${documentId}/extractions`, {
    searchParams: params,
  });
}

/** FR-EXT-004 — manual field corrections persist with the extraction record. */
export function correctExtraction(id: string, corrections: { field: string; value: unknown }[]) {
  return apiFetch<ExtractionDetail>(`/extractions/${id}`, {
    method: "PATCH",
    body: { corrections },
  });
}
