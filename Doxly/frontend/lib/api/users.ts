import { apiFetch } from "@/lib/api/client";

/** specs/api.md §2 (/users) — only what Dashboard's UsageStrip needs (FR-USER-003). */

export type UsageSummary = {
  plan: "free" | "pro";
  storage_used_bytes: number;
  storage_quota_bytes: number;
  document_count: number;
  document_quota: number | null;
  ai_requests_today: number;
  ai_requests_daily_limit: number;
};

export function getUsage() {
  return apiFetch<UsageSummary>("/users/me/usage");
}
