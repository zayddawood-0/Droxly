import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { ReactNode } from "react";

import { mswServer } from "@/lib/test/msw-server";
import { useChatStream } from "./use-chat-stream";

function sseStream(events: { event: string; data: unknown }[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const { event, data } of events) {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      }
      controller.close();
    },
  });
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useChatStream — FR-AI-001/003/005/006", () => {
  it("accumulates tokens into a draft, then clears it once the turn completes", async () => {
    mswServer.use(
      http.post("/api/v1/chat/conversations/c1/messages", () =>
        new HttpResponse(
          sseStream([
            { event: "message_id", data: { message_id: "msg_user" } },
            { event: "token", data: { text: "Revenue " } },
            { event: "token", data: { text: "grew." } },
            { event: "citations", data: { citations: [] } },
            { event: "done", data: { message_id: "msg_assistant" } },
          ]),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
      http.get("/api/v1/chat/conversations/c1", () =>
        HttpResponse.json({
          id: "c1",
          title: null,
          scope_type: "workspace",
          document_ids: [],
          created_at: "2026-01-01T00:00:00Z",
          messages: [
            { id: "msg_user", role: "user", content: "How much did revenue grow?", citations: [], created_at: "2026-01-01T00:00:00Z" },
            { id: "msg_assistant", role: "assistant", content: "Revenue grew.", citations: [], created_at: "2026-01-01T00:00:01Z" },
          ],
        }),
      ),
    );

    const { result } = renderHook(() => useChatStream("c1", undefined), { wrapper });

    await act(async () => {
      await result.current.send("How much did revenue grow?");
    });

    // Streaming finished and the hook cleared its optimistic/draft state,
    // deferring to the server's authoritative conversation data.
    await waitFor(() => {
      expect(result.current.draft).toBeNull();
      expect(result.current.optimisticUserMessage).toBeNull();
    });
  });

  it("surfaces a mid-stream error event on the draft without throwing", async () => {
    mswServer.use(
      http.post("/api/v1/chat/conversations/c1/messages", () =>
        new HttpResponse(
          sseStream([
            { event: "message_id", data: { message_id: "msg_user" } },
            { event: "token", data: { text: "partial" } },
            { event: "error", data: { code: "provider_timeout", message: "AI is taking longer than expected." } },
          ]),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream("c1", undefined), { wrapper });

    await act(async () => {
      await result.current.send("hi");
    });

    expect(result.current.draft?.status).toBe("error");
    expect(result.current.draft?.errorMessage).toBe("AI is taking longer than expected.");
  });

  it("creates a new conversation when none exists yet, then streams into it", async () => {
    mswServer.use(
      http.post("/api/v1/chat/conversations", () =>
        HttpResponse.json(
          { id: "new_c1", scope_type: "workspace", document_ids: [], title: null, created_at: "2026-01-01T00:00:00Z" },
          { status: 201 },
        ),
      ),
      http.post("/api/v1/chat/conversations/new_c1/messages", () =>
        new HttpResponse(
          sseStream([
            { event: "message_id", data: { message_id: "msg_1" } },
            { event: "token", data: { text: "Hi!" } },
            { event: "citations", data: { citations: [] } },
            { event: "done", data: { message_id: "msg_2" } },
          ]),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
      http.get("/api/v1/chat/conversations/new_c1", () =>
        HttpResponse.json({
          id: "new_c1",
          title: null,
          scope_type: "workspace",
          document_ids: [],
          created_at: "2026-01-01T00:00:00Z",
          messages: [],
        }),
      ),
    );

    const { result } = renderHook(() => useChatStream(null, undefined), { wrapper });

    let returnedId: string | undefined;
    await act(async () => {
      returnedId = await result.current.send("hello");
    });

    expect(returnedId).toBe("new_c1");
  });
});
