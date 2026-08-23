import { apiFetch } from "@/lib/api/client";

/** specs/api.md §2 (/users). */

export type UserRole = "user" | "admin";

export type CurrentUser = {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  role: UserRole;
  plan: "free" | "pro";
  email_verified: boolean;
  storage_used_bytes: number;
  created_at: string;
};

export type UsageSummary = {
  plan: "free" | "pro";
  storage_used_bytes: number;
  storage_quota_bytes: number;
  document_count: number;
  document_quota: number | null;
  ai_requests_today: number;
  ai_requests_daily_limit: number;
};

/** FR-USER-001 — used by the admin route guard (security.md §3.1) to check `role`. */
export function getCurrentUser() {
  return apiFetch<CurrentUser>("/users/me");
}

export function getUsage() {
  return apiFetch<UsageSummary>("/users/me/usage");
}
