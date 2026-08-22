import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { mswServer } from "@/lib/test/msw-server";
import { useDocumentStatusStream } from "./use-document-status-stream";
import type { DocumentDetail } from "@/lib/api/documents";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onerror: (() => void) | null = null;
  closed = false;
  private listeners: Record<string, ((event: MessageEvent<string>) => void)[]> = {};

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, callback: (event: MessageEvent<string>) => void) {
    (this.listeners[type] ??= []).push(callback);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    this.listeners[type]?.forEach((callback) => callback(event));
  }
}

function makeDocument(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    id: "doc_1",
    file_name: "invoice.pdf",
    mime_type: "application/pdf",
    size_bytes: 1024,
    status: "extracting",
    page_count: null,
    tags: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    checksum_sha256: "abc",
    processing_error: null,
    extracted_text_available: false,
    ...overrides,
  };
}

function renderWithClient(documentId: string, status: DocumentDetail["status"] | undefined, pollIntervalMs: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["documents", "detail", documentId], makeDocument({ status }));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useDocumentStatusStream(documentId, status, pollIntervalMs), { wrapper });
  return { client, ...view };
}

describe("useDocumentStatusStream — FR-DOC-008", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("applies a status event from the SSE stream into the query cache", async () => {
    const { client } = renderWithClient("doc_1", "extracting", 3000);

    expect(MockEventSource.instances).toHaveLength(1);
    const source = MockEventSource.instances[0];
    expect(source.url).toBe("/api/v1/documents/doc_1/status/stream");

    source.emit("status", { status: "chunking", processing_error: null });

    await waitFor(() => {
      expect(client.getQueryData<DocumentDetail>(["documents", "detail", "doc_1"])?.status).toBe(
        "chunking",
      );
    });
  });

  it("falls back to polling GET .../status when the stream errors", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1/status", () =>
        HttpResponse.json({ status: "ready", processing_error: null }),
      ),
    );

    const { client } = renderWithClient("doc_1", "embedding", 10);
    const source = MockEventSource.instances[0];

    source.onerror?.();

    await waitFor(
      () => {
        expect(client.getQueryData<DocumentDetail>(["documents", "detail", "doc_1"])?.status).toBe(
          "ready",
        );
      },
      { timeout: 2000 },
    );
    expect(source.closed).toBe(true);
  });

  it("never opens a connection for an already-terminal status", () => {
    renderWithClient("doc_1", "ready", 3000);
    expect(MockEventSource.instances).toHaveLength(0);
  });
});
