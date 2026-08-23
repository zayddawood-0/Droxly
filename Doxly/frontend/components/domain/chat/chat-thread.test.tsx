import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { ChatThread } from "./chat-thread";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const baseConversation = {
  id: "conv_1",
  title: "My conversation",
  scope_type: "single_document",
  document_ids: ["doc_1"],
  created_at: "2026-01-01T00:00:00Z",
};

describe("ChatThread — FR-AI-001/003", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    // jsdom doesn't implement scrollTo; ChatThread calls it to keep the
    // thread pinned to the latest message.
    Element.prototype.scrollTo = vi.fn();
  });

  it("shows a not-found (404) state distinctly from a generic load failure, with no retry", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations/conv_1", () =>
        HttpResponse.json({ error: { code: "not_found", message: "..." } }, { status: 404 }),
      ),
    );

    renderWithProviders(<ChatThread conversationId="conv_1" />);

    expect(
      await screen.findByText("This conversation doesn't exist, or you don't have access to it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("shows a generic connectivity error with a retry action for a non-404 failure", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations/conv_1", () =>
        HttpResponse.json({ error: { code: "server_error", message: "..." } }, { status: 500 }),
      ),
    );

    renderWithProviders(<ChatThread conversationId="conv_1" />);

    expect(
      await screen.findByText("We couldn't load this conversation right now."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows the empty-thread prompt for a conversation with no messages yet", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations/conv_1", () =>
        HttpResponse.json({ ...baseConversation, messages: [] }),
      ),
    );

    renderWithProviders(<ChatThread conversationId="conv_1" />);

    expect(await screen.findByText("Ask a question about your documents")).toBeInTheDocument();
  });

  it("renders persisted messages with their citations once loaded", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations/conv_1", () =>
        HttpResponse.json({
          ...baseConversation,
          messages: [
            { id: "msg_1", role: "user", content: "What's the total?", citations: [], created_at: "2026-01-01T00:00:00Z" },
            {
              id: "msg_2",
              role: "assistant",
              content: "The total is $500.",
              citations: [{ document_id: "doc_1", page_number: 2, snippet: "Total: $500", relevance_score: 0.9 }],
              created_at: "2026-01-01T00:00:01Z",
            },
          ],
        }),
      ),
    );

    renderWithProviders(<ChatThread conversationId="conv_1" />);

    expect(await screen.findByText("What's the total?")).toBeInTheDocument();
    expect(screen.getByText("The total is $500.")).toBeInTheDocument();
  });

  it("shows the document scope picker only for a new (no conversationId) thread", () => {
    renderWithProviders(<ChatThread conversationId={null} />);

    expect(screen.getByRole("button", { name: /All documents/ })).toBeInTheDocument();
  });
});
