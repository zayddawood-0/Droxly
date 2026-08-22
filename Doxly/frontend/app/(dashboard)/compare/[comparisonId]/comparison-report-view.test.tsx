import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { Toaster } from "@/components/ui/sonner";
import { ComparisonReportView } from "./comparison-report-view";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {ui}
      <Toaster />
    </QueryClientProvider>,
  );
}

const baseComparison = {
  id: "cmp_1",
  document_a_id: "doc_a",
  document_b_id: "doc_b",
  created_at: "2026-01-01T00:00:00Z",
};

function mockDocuments() {
  mswServer.use(
    http.get("/api/v1/documents/doc_a", () =>
      HttpResponse.json({ id: "doc_a", file_name: "contract-v1.pdf" }),
    ),
    http.get("/api/v1/documents/doc_b", () =>
      HttpResponse.json({ id: "doc_b", file_name: "contract-v2.pdf" }),
    ),
  );
}

describe("ComparisonReportView — FR-COMP-001/002/003", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    );
    mockDocuments();
  });

  it("polls a processing comparison until it completes and renders the diff", async () => {
    let callCount = 0;
    mswServer.use(
      http.get("/api/v1/comparisons/cmp_1", () => {
        callCount += 1;
        const completed = callCount >= 2;
        return HttpResponse.json({
          ...baseComparison,
          status: completed ? "completed" : "processing",
          result: completed
            ? {
                alignment_quality: "high",
                message: null,
                additions: [{ document: "b", page_number: 1, excerpt: "New clause" }],
                deletions: [],
                modifications: [],
              }
            : null,
        });
      }),
    );

    renderWithProviders(<ComparisonReportView comparisonId="cmp_1" />);

    expect(await screen.findByText("Comparing your documents…")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getAllByText(/New clause/).length).toBeGreaterThan(0);
      },
      { timeout: 4000 },
    );
  });

  it("renders the degraded-alignment path instead of a forced diff", async () => {
    mswServer.use(
      http.get("/api/v1/comparisons/cmp_1", () =>
        HttpResponse.json({
          ...baseComparison,
          status: "completed",
          result: {
            alignment_quality: "low",
            message: "These documents are too different to align meaningfully.",
            additions: [],
            deletions: [],
            modifications: [],
          },
        }),
      ),
    );

    renderWithProviders(<ComparisonReportView comparisonId="cmp_1" />);

    expect(
      await screen.findByText("These documents are too different to align meaningfully."),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /View contract-v1.pdf/ })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /View contract-v2.pdf/ })).toBeInTheDocument();
  });

  it("shows a Retry action for a failed comparison", async () => {
    mswServer.use(
      http.get("/api/v1/comparisons/cmp_1", () =>
        HttpResponse.json({ ...baseComparison, status: "failed", result: null }),
      ),
    );

    renderWithProviders(<ComparisonReportView comparisonId="cmp_1" />);

    expect(await screen.findByText("This comparison couldn't be completed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows a not-found (404) state distinctly from a generic load failure", async () => {
    mswServer.use(
      http.get("/api/v1/comparisons/cmp_1", () =>
        HttpResponse.json({ error: { code: "not_found", message: "..." } }, { status: 404 }),
      ),
    );

    renderWithProviders(<ComparisonReportView comparisonId="cmp_1" />);

    expect(
      await screen.findByText("This comparison doesn't exist, or you don't have access to it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
