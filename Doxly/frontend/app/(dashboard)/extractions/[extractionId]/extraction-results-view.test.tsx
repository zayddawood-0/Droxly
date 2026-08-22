import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { Toaster } from "@/components/ui/sonner";
import { ExtractionResultsView } from "./extraction-results-view";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {ui}
      <Toaster />
    </QueryClientProvider>,
  );
}

const baseExtraction = {
  id: "ext_1",
  document_id: "doc_1",
  template_key: "invoice",
  schema: [{ name: "vendor_name", type: "string", required: true }],
  created_at: "2026-01-01T00:00:00Z",
};

describe("ExtractionResultsView — FR-EXT-001/003/004", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    );
  });

  it("polls a processing extraction until it completes and shows the coverage toast", async () => {
    let callCount = 0;
    mswServer.use(
      http.get("/api/v1/extractions/ext_1", () => {
        callCount += 1;
        const completed = callCount >= 2;
        return HttpResponse.json({
          ...baseExtraction,
          status: completed ? "completed" : "processing",
          result: completed
            ? [
                {
                  field: "vendor_name",
                  value: "Acme Corp",
                  confidence: 0.9,
                  not_found_reason: null,
                  corrected: false,
                  citation: { page_number: 1, snippet: "Acme Corp" },
                },
              ]
            : [],
        });
      }),
    );

    renderWithProviders(<ExtractionResultsView extractionId="ext_1" />);

    expect(await screen.findByText("Extracting fields from your document…")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getAllByText("Acme Corp").length).toBeGreaterThan(0);
      },
      { timeout: 4000 },
    );
    expect(await screen.findByText("Extraction complete — 1 of 1 fields found")).toBeInTheDocument();
  });

  it("shows a not-found field distinctly and saves a correction", async () => {
    mswServer.use(
      http.get("/api/v1/extractions/ext_1", () =>
        HttpResponse.json({
          ...baseExtraction,
          status: "completed",
          result: [
            {
              field: "vendor_name",
              value: null,
              confidence: null,
              not_found_reason: "not mentioned in the document",
              corrected: false,
              citation: null,
            },
          ],
        }),
      ),
      http.patch("/api/v1/extractions/ext_1", () =>
        HttpResponse.json({
          ...baseExtraction,
          status: "completed",
          result: [
            {
              field: "vendor_name",
              value: "Acme Corp",
              confidence: null,
              not_found_reason: null,
              corrected: true,
              citation: null,
            },
          ],
        }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<ExtractionResultsView extractionId="ext_1" />);

    // Both the desktop table row and the mobile card render simultaneously
    // in jsdom (no real CSS media-query viewport filtering) — the visible
    // pair is intentional per ui-ux.md §10's responsive spec, so tests
    // interact with the first match rather than assuming a single one.
    await waitFor(() => {
      expect(screen.getAllByText("Not found in document").length).toBeGreaterThan(0);
    });

    await user.click((await screen.findAllByRole("button", { name: "Edit vendor_name" }))[0]);
    await user.type(screen.getAllByLabelText("Edit value for vendor_name")[0], "Acme Corp{Enter}");

    await waitFor(() => {
      expect(screen.getAllByText("Acme Corp").length).toBeGreaterThan(0);
    });
  });

  it("shows a Retry action for a failed extraction", async () => {
    mswServer.use(
      http.get("/api/v1/extractions/ext_1", () =>
        HttpResponse.json({ ...baseExtraction, status: "failed", result: [] }),
      ),
    );

    renderWithProviders(<ExtractionResultsView extractionId="ext_1" />);

    expect(await screen.findByText("This extraction couldn't be completed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows a not-found (404) state distinctly from a generic load failure", async () => {
    mswServer.use(
      http.get("/api/v1/extractions/ext_1", () =>
        HttpResponse.json({ error: { code: "not_found", message: "..." } }, { status: 404 }),
      ),
    );

    renderWithProviders(<ExtractionResultsView extractionId="ext_1" />);

    expect(
      await screen.findByText("This extraction doesn't exist, or you don't have access to it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
