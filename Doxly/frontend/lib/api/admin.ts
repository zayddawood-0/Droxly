import { apiFetch } from "@/lib/api/client";

/** One function per documented endpoint in specs/api.md §12 (/admin). */

export type AdminUserStatus = "active" | "suspended" | "pending_deletion";
export type AdminUserPlan = "free" | "pro";
export type AdminUserRole = "user" | "admin";

export type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  plan: AdminUserPlan;
  status: AdminUserStatus;
  role: AdminUserRole;
  created_at: string;
};

export type PaginatedAdminUsers = {
  items: AdminUser[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminUserListParams = {
  limit?: number;
  offset?: number;
  status?: AdminUserStatus;
  plan?: AdminUserPlan;
};

export type SystemHealth = {
  queue_depth: number;
  processing_failure_rate_24h: number;
  ai_requests_24h: number;
  ai_error_rate_24h: number;
};

/** FR-ADMIN-001 */
export function listAdminUsers(params: AdminUserListParams) {
  return apiFetch<PaginatedAdminUsers>("/admin/users", { searchParams: params });
}

/** FR-ADMIN-002 */
export function getSystemHealth() {
  return apiFetch<SystemHealth>("/admin/system/health");
}

/** FR-ADMIN-003 */
export function suspendUser(id: string, reason: string) {
  return apiFetch<{ id: string; status: "suspended" }>(`/admin/users/${id}/suspend`, {
    method: "POST",
    body: { reason },
  });
}

/** FR-ADMIN-003 */
export function unsuspendUser(id: string) {
  return apiFetch<{ id: string; status: "active" }>(`/admin/users/${id}/unsuspend`, {
    method: "POST",
  });
}
