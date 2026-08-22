import { describe, expect, it } from "vitest";
import { isConnectivityError } from "./error-messages";
import { DoxlyApiError } from "@/lib/types/errors";

describe("isConnectivityError", () => {
  it("is true for a raw thrown error (network failure, offline, DNS)", () => {
    expect(isConnectivityError(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("is true for a 5xx DoxlyApiError", () => {
    const error = new DoxlyApiError(502, {
      error: { code: "upstream_unavailable", message: "..." },
    });
    expect(isConnectivityError(error)).toBe(true);
  });

  it("is false for a 4xx DoxlyApiError — that's a request-level problem", () => {
    const error = new DoxlyApiError(401, {
      error: { code: "invalid_credentials", message: "..." },
    });
    expect(isConnectivityError(error)).toBe(false);
  });
});
