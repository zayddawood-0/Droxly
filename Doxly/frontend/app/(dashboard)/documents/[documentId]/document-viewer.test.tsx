import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { Toaster } from "@/components/ui/sonner";
import { DocumentViewer } from "./document-viewer";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

class MockEventSource {
  onerror: (() => void) | null = null;
  addEventListener() {}
  close() {}
  constructor(public url: string) {}
}

function renderViewer(documentId = "doc_1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DocumentViewer documentId={documentId} />
      <Toaster />
    </QueryClientProvider>,
  );
}

const baseDocument = {
  id: "doc_1",
  file_name: "contract.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  page_count: 3,
  tags: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  checksum_sha256: "abc",
  extracted_text_available: false,
};

describe("DocumentViewer — FR-DOC-003, FR-DOC-008, FR-PROC-005", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", MockEventSource);
    // sonner's Toaster reads prefers-color-scheme via matchMedia, which
    // jsdom doesn't implement — only needed here since this is the one
    // test file that mounts <Toaster/> to observe toast output.
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    );
    mswServer.use(http.get("/api/v1/tags", () => HttpResponse.json({ items: [] })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the shared stage badge and description for an in-progress document", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1", () =>
        HttpResponse.json({ ...baseDocument, status: "chunking", processing_error: null }),
      ),
    );

    renderViewer();

    await waitFor(() => {
      expect(screen.getAllByText("Chunking").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByText("Splitting the extracted text into searchable sections."),
    ).toBeInTheDocument();
  });

  it("shows a Retry processing action for a failed document, and reprocessing moves it back to queued", async () => {
    // Stateful, like a real backend: the detail GET reflects "failed" until
    // reprocess is called, then "queued" — this is what makes the
    // mutation's invalidateQueries(["documents"]) refetch meaningful rather
    // than immediately clobbering the optimistic cache update with stale data.
    let reprocessed = false;
    mswServer.use(
      http.get("/api/v1/documents/doc_1", () =>
        HttpResponse.json({
          ...baseDocument,
          status: reprocessed ? "queued" : "failed",
          processing_error: reprocessed ? null : "The file appears to be password-protected.",
        }),
      ),
      http.post("/api/v1/documents/doc_1/reprocess", () => {
        reprocessed = true;
        return HttpResponse.json({ id: "doc_1", status: "queued" }, { status: 202 });
      }),
    );

    const user = userEvent.setup();
    renderViewer();

    expect(await screen.findByText("Processing failed")).toBeInTheDocument();
    expect(
      screen.getByText("The file appears to be password-protected."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry processing" }));

    await waitFor(() => {
      expect(screen.queryByText("Processing failed")).not.toBeInTheDocument();
    });
    expect(screen.getAllByText("Queued").length).toBeGreaterThan(0);
  });

  it("surfaces a connectivity-safe error toast when reprocessing itself fails", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1", () =>
        HttpResponse.json({
          ...baseDocument,
          status: "failed",
          processing_error: "Corrupt file.",
        }),
      ),
      http.post("/api/v1/documents/doc_1/reprocess", () =>
        HttpResponse.json(
          { error: { code: "invalid_status", message: "..." } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderViewer();

    await user.click(await screen.findByRole("button", { name: "Retry processing" }));

    expect(
      await screen.findByText("Couldn't restart processing. Please try again."),
    ).toBeInTheDocument();
  });
});
