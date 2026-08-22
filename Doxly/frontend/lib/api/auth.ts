import { apiFetch } from "@/lib/api/client";

/**
 * One function per documented endpoint in specs/api.md §1 (/auth) — no
 * scattered fetch() calls in form components (skills/frontend.md §9).
 * Every shape below mirrors that spec's request/response fields exactly.
 */

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  email_verified: boolean;
};

export type LoginResponse = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  plan: string;
};

/** FR-AUTH-001 */
export function register(input: {
  email: string;
  password: string;
  display_name: string;
}) {
  return apiFetch<AuthUser>("/auth/register", { method: "POST", body: input });
}

/** FR-AUTH-004 */
export function login(input: { email: string; password: string }) {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: input,
  });
}

/** FR-AUTH-006 */
export function logout() {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

/** FR-AUTH-002 — the emailed link opens a Next.js page that POSTs the token here (BFF pattern, api.md §1). */
export function verifyEmail(token: string) {
  return apiFetch<{ verified: true }>("/auth/verify-email", {
    method: "POST",
    body: { token },
  });
}

/** FR-AUTH-007, step 1 — always 202 regardless of whether the email exists (NFR-SEC-006). */
export function requestPasswordReset(email: string) {
  return apiFetch<void>("/auth/password-reset/request", {
    method: "POST",
    body: { email },
  });
}

/** FR-AUTH-007, step 2 */
export function confirmPasswordReset(input: {
  token: string;
  new_password: string;
}) {
  return apiFetch<{ reset: true }>("/auth/password-reset/confirm", {
    method: "POST",
    body: input,
  });
}

/**
 * FR-AUTH-003 — Google OAuth is a full-page redirect flow (GET, 302 to
 * Google's consent screen), never a fetch() call. Callers navigate the
 * browser to this path directly (an <a href> / window.location assignment).
 */
export const GOOGLE_OAUTH_START_PATH = "/api/v1/auth/oauth/google";
