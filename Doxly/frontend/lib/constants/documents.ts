/**
 * Single source for the numbers that would otherwise get hardcoded into
 * every upload/quota-adjacent component — flagged as a gap in the Phase 1
 * plan (specs/decisions.md OQ-06/OQ-07 are still "Assumption" status, not
 * finalized product values). One place to update when product confirms
 * different numbers.
 */

export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // decisions.md OQ-06

export const ACCEPTED_MIME_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/csv",
] as const;

export type AcceptedMimeType = (typeof ACCEPTED_MIME_TYPES)[number];

export const ACCEPTED_FILE_EXTENSIONS = [".pdf", ".docx", ".txt", ".csv"];

export const ACCEPTED_TYPES_LABEL = "PDF, DOCX, TXT, or CSV";

// decisions.md OQ-07
export const PLAN_QUOTAS = {
  free: { storageBytes: 100 * 1024 * 1024, documentLimit: 10 },
  pro: { storageBytes: 5 * 1024 * 1024 * 1024, documentLimit: null as number | null },
} as const;

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`;
}
