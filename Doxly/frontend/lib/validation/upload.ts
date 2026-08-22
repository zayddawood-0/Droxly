import {
  ACCEPTED_MIME_TYPES,
  ACCEPTED_TYPES_LABEL,
  MAX_FILE_SIZE_BYTES,
  formatBytes,
} from "@/lib/constants/documents";

/**
 * Client-side validation is a UX convenience only, never the security
 * boundary (skills/frontend.md §8) — content-sniffed MIME validation is
 * server-side (specs/security.md §5). This just gives fast, specific
 * feedback before a network call, per ui-ux.md §6.
 */
export function validateFileForUpload(file: File): string | null {
  const looksAccepted =
    ACCEPTED_MIME_TYPES.includes(file.type as (typeof ACCEPTED_MIME_TYPES)[number]) ||
    /\.(pdf|docx|txt|csv)$/i.test(file.name);

  if (!looksAccepted) {
    return `Unsupported file type — ${ACCEPTED_TYPES_LABEL} only`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `File exceeds the ${formatBytes(MAX_FILE_SIZE_BYTES)} limit`;
  }
  if (file.size === 0) {
    return "This file is empty";
  }
  return null;
}
