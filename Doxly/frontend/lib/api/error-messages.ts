import { isDoxlyApiError } from "@/lib/types/errors";

/**
 * True for errors that mean "the request itself couldn't be completed"
 * (offline, DNS failure, an unexpected 5xx, or this app's own BFF proxy
 * returning 502 because no backend is reachable yet) — rendered as a
 * dismissible banner, per specs/ui-ux.md §2, never blamed on what the user
 * typed. A 4xx is always a request-level problem, handled inline by the
 * caller instead.
 */
export function isConnectivityError(error: unknown): boolean {
  if (!isDoxlyApiError(error)) return true;
  return error.status >= 500;
}

export const CONNECTIVITY_ERROR_MESSAGE =
  "We couldn't reach Doxly. Check your connection and try again.";

export const RATE_LIMITED_MESSAGE =
  "Too many attempts. Please wait a moment and try again.";
