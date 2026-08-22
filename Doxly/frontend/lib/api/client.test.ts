import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./client";
import { DoxlyApiError, isDoxlyApiError } from "@/lib/types/errors";

function mockFetchOnce(response: {
  status: number;
  body?: unknown;
  contentType?: string;
}) {
  const { status, body, contentType = "application/json" } = response;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      ok: status >= 200 && status < 300,
      headers: { get: (name: string) => (name === "content-type" ? contentType : null) },
      json: async () => body,
    }),
  );
}

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed JSON body on success", async () => {
    mockFetchOnce({ status: 200, body: { id: "doc_1" } });
    const result = await apiFetch<{ id: string }>("/documents/doc_1");
    expect(result).toEqual({ id: "doc_1" });
  });

  it("returns undefined for a 204 No Content response", async () => {
    mockFetchOnce({ status: 204 });
    const result = await apiFetch("/documents/doc_1");
    expect(result).toBeUndefined();
  });

  it("throws a typed DoxlyApiError matching the api.md §0.5 envelope on failure", async () => {
    mockFetchOnce({
      status: 404,
      body: { error: { code: "document_not_found", message: "Not found." } },
    });

    await expect(apiFetch("/documents/missing")).rejects.toSatisfy(
      (err: unknown) => {
        expect(isDoxlyApiError(err)).toBe(true);
        const apiError = err as DoxlyApiError;
        expect(apiError.status).toBe(404);
        expect(apiError.code).toBe("document_not_found");
        expect(apiError.message).toBe("Not found.");
        return true;
      },
    );
  });

  it("exposes validation field errors from a 422 response", async () => {
    mockFetchOnce({
      status: 422,
      body: {
        error: {
          code: "validation_error",
          message: "Invalid request.",
          fields: { email: "not a valid email" },
        },
      },
    });

    try {
      await apiFetch("/auth/register");
      expect.unreachable("expected apiFetch to throw");
    } catch (err) {
      const apiError = err as DoxlyApiError;
      expect(apiError.isValidationError).toBe(true);
      expect(apiError.fields).toEqual({ email: "not a valid email" });
    }
  });
});

describe("apiFetch — session refresh (FR-AUTH-005)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mockResponse(status: number, body?: unknown) {
    return {
      status,
      ok: status >= 200 && status < 300,
      headers: { get: () => "application/json" },
      json: async () => body,
    };
  }

  it("refreshes once and retries the original request after a 401", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      calls.push(url);
      if (url.includes("/documents/doc_1") && calls.filter((c) => c === url).length === 1) {
        return mockResponse(401, { error: { code: "token_expired", message: "..." } });
      }
      if (url.includes("/auth/refresh")) {
        return mockResponse(200);
      }
      return mockResponse(200, { id: "doc_1" });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiFetch<{ id: string }>("/documents/doc_1");

    expect(result).toEqual({ id: "doc_1" });
    expect(calls.filter((c) => c.includes("/auth/refresh"))).toHaveLength(1);
    expect(calls.filter((c) => c.includes("/documents/doc_1"))).toHaveLength(2);
  });

  it("surfaces the original 401 when refresh itself fails", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) return mockResponse(401);
      return mockResponse(401, { error: { code: "token_expired", message: "Session expired." } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/documents/doc_1")).rejects.toSatisfy((err: unknown) => {
      expect(isDoxlyApiError(err)).toBe(true);
      expect((err as DoxlyApiError).status).toBe(401);
      return true;
    });
  });

  it("never attempts a refresh for a 401 on /auth/login itself", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) throw new Error("should not be called");
      return mockResponse(401, { error: { code: "invalid_credentials", message: "..." } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiFetch("/auth/login", { method: "POST", body: {} }),
    ).rejects.toSatisfy((err: unknown) => {
      expect((err as DoxlyApiError).status).toBe(401);
      return true;
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
