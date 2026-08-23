import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { Toaster } from "@/components/ui/sonner";
import { ConversationList } from "./conversation-list";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {ui}
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("ConversationList — FR-AI-003", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    );
  });

  it("shows a connectivity error with retry, not a blank sidebar", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations", () =>
        HttpResponse.json({ error: { code: "server_error", message: "..." } }, { status: 500 }),
      ),
    );

    renderWithProviders(<ConversationList activeConversationId={null} />);

    expect(await screen.findByText("Couldn't load your conversations.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows a distinct empty state when there are no conversations yet", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations", () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
    );

    renderWithProviders(<ConversationList activeConversationId={null} />);

    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
  });

  it("lists conversations, highlighting the active one and showing scope", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations", () =>
        HttpResponse.json({
          items: [
            { id: "conv_1", title: "Lease questions", scope_type: "single_document", document_ids: ["doc_1"], updated_at: "2026-01-01T00:00:00Z" },
            { id: "conv_2", title: null, scope_type: "workspace", document_ids: [], updated_at: "2026-01-02T00:00:00Z" },
          ],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      ),
    );

    renderWithProviders(<ConversationList activeConversationId="conv_1" />);

    expect(await screen.findByText("Lease questions")).toBeInTheDocument();
    expect(screen.getByText("New conversation")).toBeInTheDocument();
    expect(screen.getByText("All documents")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Lease questions/ })).toHaveClass("bg-accent");
  });

  it("deletes a conversation and shows a success toast", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations", () =>
        HttpResponse.json({
          items: [
            { id: "conv_1", title: "Lease questions", scope_type: "single_document", document_ids: ["doc_1"], updated_at: "2026-01-01T00:00:00Z" },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
      http.delete("/api/v1/chat/conversations/conv_1", () => new HttpResponse(null, { status: 204 })),
    );

    const user = userEvent.setup();
    renderWithProviders(<ConversationList activeConversationId={null} />);

    await user.click(await screen.findByRole("button", { name: /Delete conversation/ }));
    expect(await screen.findByText("Conversation deleted")).toBeInTheDocument();
  });

  it("shows a non-connectivity error toast with its own message when deletion is rejected (e.g. already deleted)", async () => {
    mswServer.use(
      http.get("/api/v1/chat/conversations", () =>
        HttpResponse.json({
          items: [
            { id: "conv_1", title: "Lease questions", scope_type: "single_document", document_ids: ["doc_1"], updated_at: "2026-01-01T00:00:00Z" },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
      http.delete("/api/v1/chat/conversations/conv_1", () =>
        HttpResponse.json({ error: { code: "not_found", message: "..." } }, { status: 404 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<ConversationList activeConversationId={null} />);

    await user.click(await screen.findByRole("button", { name: /Delete conversation/ }));
    expect(
      await screen.findByText("Couldn't delete this conversation. Please try again."),
    ).toBeInTheDocument();
  });
});
