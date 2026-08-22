import { DoxlyApiError, type ApiErrorBody } from "@/lib/types/errors";

const API_PREFIX = "/api/v1";

type ApiFetchOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  searchParams?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
};

const MUTATING_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

// Requests that must never trigger a refresh-and-retry — retrying a failed
// login/refresh call against itself would either loop or mask the real error
// (e.g. a 401 from /auth/login means "wrong password," not "expired session").
const REFRESH_EXEMPT_PATHS = new Set(["/auth/refresh", "/auth/login"]);

/**
 * The one client-side entry point every domain module (lib/api/auth.ts,
 * lib/api/documents.ts, …) is built on — no raw fetch() in components
 * (skills/frontend.md §9). Calls stay same-origin against this Next.js app's
 * own /api/v1/* Route Handlers, which proxy to FastAPI (see
 * app/api/v1/[...path]/route.ts) — this module never talks to the backend
 * origin directly, preserving the BFF boundary in specs/architecture.md §2.1.
 *
 * Error handling: any non-2xx response is parsed against the api.md §0.5
 * envelope and thrown as a typed DoxlyApiError — callers branch on
 * `.status`/`.code`, never on parsing response text themselves.
 *
 * Session refresh (FR-AUTH-005): a 401 on any request other than login/
 * refresh itself triggers one silent POST /auth/refresh, then a single retry
 * of the original request — never a user-visible re-login prompt for a
 * merely-expired access token. Concurrent 401s share one in-flight refresh
 * (deduped below) rather than each firing their own.
 */
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const response = await rawFetch(path, options);

  if (response.status === 401 && !REFRESH_EXEMPT_PATHS.has(path)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return parseResponse<T>(await rawFetch(path, options));
    }
  }

  return parseResponse<T>(response);
}

function rawFetch(path: string, options: ApiFetchOptions) {
  const { method = "GET", body, searchParams, signal } = options;

  const url = new URL(`${API_PREFIX}${path}`, "http://placeholder");
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  // CSRF double-submit (specs/security.md §6.3): the BFF issues a readable,
  // non-httpOnly "csrf_token" cookie on session start. Every mutating request
  // echoes it back in a custom header; FastAPI verifies the two match before
  // processing. No-op until a backend actually sets that cookie.
  if (MUTATING_METHODS.has(method)) {
    const csrfToken = readCookie("csrf_token");
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }

  return fetch(`${url.pathname}${url.search}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  const payload = isJson ? await response.json() : undefined;

  if (!response.ok) {
    throw new DoxlyApiError(response.status, payload as ApiErrorBody);
  }

  return payload as T;
}

let refreshInFlight: Promise<boolean> | null = null;

/** Cookie-driven (specs/api.md §1's POST /auth/refresh) — resolves true only on a 2xx. */
function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = rawFetch("/auth/refresh", { method: "POST" })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : undefined;
}
