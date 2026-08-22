import { apiFetch } from "@/lib/api/client";
import type { DocumentTagRef } from "@/lib/api/documents";

/** specs/api.md §3 (/tags) — FR-DOC-006. */

export function listTags() {
  return apiFetch<{ items: DocumentTagRef[] }>("/tags");
}

export function createTag(input: { name: string; color?: string }) {
  return apiFetch<DocumentTagRef>("/tags", { method: "POST", body: input });
}

export function deleteTag(id: string) {
  return apiFetch<void>(`/tags/${id}`, { method: "DELETE" });
}
