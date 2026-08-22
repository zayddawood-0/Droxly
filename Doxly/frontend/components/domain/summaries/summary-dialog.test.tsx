import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { SummaryDialog } from "./summary-dialog";

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("SummaryDialog — FR-SUM-001, FR-SUM-002", () => {
  it("shows the generate form directly when no summaries exist yet", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1/summaries", () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    );

    renderWithQueryClient(<SummaryDialog documentId="doc_1" open onOpenChange={() => {}} />);

    expect(await screen.findByText("No summaries yet — generate one above.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate/i })).toBeInTheDocument();
  });

  it("lists past summaries, newest first, and expands one to show completed content", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1/summaries", () =>
        HttpResponse.json({
          items: [
            { id: "sum_1", summary_type: "brief", status: "completed", created_at: "2026-01-02T00:00:00Z" },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
      http.get("/api/v1/summaries/sum_1", () =>
        HttpResponse.json({
          id: "sum_1",
          document_id: "doc_1",
          summary_type: "brief",
          status: "completed",
          content: "This document covers quarterly revenue growth.",
          created_at: "2026-01-02T00:00:00Z",
        }),
      ),
    );

    const user = userEvent.setup();
    renderWithQueryClient(<SummaryDialog documentId="doc_1" open onOpenChange={() => {}} />);

    await user.click(await screen.findByRole("button", { name: /expand brief summary/i }));

    expect(
      await screen.findByText("This document covers quarterly revenue growth."),
    ).toBeInTheDocument();
  });

  it("renders bullet_points content as a real list, not literal dashes", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1/summaries", () =>
        HttpResponse.json({
          items: [
            { id: "sum_1", summary_type: "bullet_points", status: "completed", created_at: "2026-01-02T00:00:00Z" },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
      http.get("/api/v1/summaries/sum_1", () =>
        HttpResponse.json({
          id: "sum_1",
          document_id: "doc_1",
          summary_type: "bullet_points",
          status: "completed",
          content: "- Revenue grew 12%\n- Costs decreased",
          created_at: "2026-01-02T00:00:00Z",
        }),
      ),
    );

    const user = userEvent.setup();
    renderWithQueryClient(<SummaryDialog documentId="doc_1" open onOpenChange={() => {}} />);

    await user.click(await screen.findByRole("button", { name: /expand bullet points summary/i }));

    const list = await screen.findByRole("list");
    expect(list.tagName).toBe("UL");
    expect(screen.getByText("Revenue grew 12%")).toBeInTheDocument();
    expect(screen.queryByText(/^- /)).not.toBeInTheDocument();
  });

  it("shows Retry on a failed summary and re-submits the same type", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1/summaries", () =>
        HttpResponse.json({
          items: [
            { id: "sum_1", summary_type: "detailed", status: "failed", created_at: "2026-01-02T00:00:00Z" },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
      http.get("/api/v1/summaries/sum_1", () =>
        HttpResponse.json({
          id: "sum_1",
          document_id: "doc_1",
          summary_type: "detailed",
          status: "failed",
          content: null,
          created_at: "2026-01-02T00:00:00Z",
        }),
      ),
      http.post("/api/v1/documents/doc_1/summaries", () =>
        HttpResponse.json(
          { id: "sum_2", document_id: "doc_1", summary_type: "detailed", status: "processing" },
          { status: 202 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithQueryClient(<SummaryDialog documentId="doc_1" open onOpenChange={() => {}} />);

    await user.click(await screen.findByRole("button", { name: /expand detailed summary/i }));
    expect(await screen.findByText("This summary couldn't be generated.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    // A new request was submitted rather than mutating the failed row in place.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /generate/i })).not.toBeDisabled();
    });
  });

  it("polls a processing summary until it completes, per FR-SUM-001's polling result view", async () => {
    let callCount = 0;
    mswServer.use(
      http.get("/api/v1/documents/doc_1/summaries", () =>
        HttpResponse.json({
          items: [
            { id: "sum_1", summary_type: "brief", status: "processing", created_at: "2026-01-02T00:00:00Z" },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
      http.get("/api/v1/summaries/sum_1", () => {
        callCount += 1;
        const completed = callCount >= 2;
        return HttpResponse.json({
          id: "sum_1",
          document_id: "doc_1",
          summary_type: "brief",
          status: completed ? "completed" : "processing",
          content: completed ? "Final summary content." : null,
          created_at: "2026-01-02T00:00:00Z",
        });
      }),
    );

    const user = userEvent.setup();
    renderWithQueryClient(<SummaryDialog documentId="doc_1" open onOpenChange={() => {}} />);

    await user.click(await screen.findByRole("button", { name: /expand brief summary/i }));
    expect(
      await screen.findByText("Generating your summary — this can take a moment."),
    ).toBeInTheDocument();

    expect(await screen.findByText("Final summary content.", {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it("shows a retry affordance when the summaries list itself fails to load", async () => {
    mswServer.use(
      http.get("/api/v1/documents/doc_1/summaries", () => HttpResponse.json({ error: {} }, { status: 502 })),
    );

    renderWithQueryClient(<SummaryDialog documentId="doc_1" open onOpenChange={() => {}} />);

    expect(await screen.findByText("Couldn't load past summaries.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
