import { z } from "zod";

/** Mirrors api.md §3's PATCH /documents/{id} and POST /tags request validation. */

export const renameDocumentSchema = z.object({
  file_name: z.string().trim().min(1, "Enter a document name"),
});
export type RenameDocumentValues = z.infer<typeof renameDocumentSchema>;

export const createTagSchema = z.object({
  name: z.string().trim().min(1, "Enter a tag name"),
});
export type CreateTagValues = z.infer<typeof createTagSchema>;
