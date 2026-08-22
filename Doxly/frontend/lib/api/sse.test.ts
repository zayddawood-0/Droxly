import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { consumeEventStream } from "./sse";
import { DoxlyApiError } from "@/lib/types/errors";

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

describe("consumeEventStream — api.md §4's SSE transport contract", () => {
  it("parses every event in order and hands each to the callback", async () => {
    mswServer.use(
      http.post("/api/v1/chat/conversations/c1/messages", () =>
        new HttpResponse(
          sseStream([
            { event: "message_id", data: { message_id: "msg_1" } },
            { event: "token", data: { text: "Hello " } },
            { event: "token", data: { text: "world" } },
            { event: "citations", data: { citations: [{ document_id: "doc_1", page_number: 2, snippet: "...", relevance_score: 0.9 }] } },
            { event: "done", data: { message_id: "msg_2" } },
          ]),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
    );

    const received: { event: string; data: unknown }[] = [];
    await consumeEventStream(
      "/chat/conversations/c1/messages",
      { content: "hi" },
      (event, data) => received.push({ event, data }),
    );

    expect(received.map((e) => e.event)).toEqual(["message_id", "token", "token", "citations", "done"]);
    expect(received[1].data).toEqual({ text: "Hello " });
    expect(received[4].data).toEqual({ message_id: "msg_2" });
  });

  it("throws a DoxlyApiError when the response is non-2xx, per 'errors returned as standard JSON before the stream opens'", async () => {
    mswServer.use(
      http.post("/api/v1/chat/conversations/c1/messages", () =>
        HttpResponse.json({ error: { code: "document_not_ready", message: "..." } }, { status: 409 }),
      ),
    );

    await expect(
      consumeEventStream("/chat/conversations/c1/messages", { content: "hi" }, () => {}),
    ).rejects.toThrow(DoxlyApiError);
  });

  it("delivers a mid-stream error event to the callback rather than throwing", async () => {
    mswServer.use(
      http.post("/api/v1/chat/conversations/c1/messages", () =>
        new HttpResponse(
          sseStream([
            { event: "message_id", data: { message_id: "msg_1" } },
            { event: "token", data: { text: "partial" } },
            { event: "error", data: { code: "provider_timeout", message: "AI is taking longer than expected." } },
          ]),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
    );

    const received: { event: string; data: unknown }[] = [];
    await consumeEventStream("/chat/conversations/c1/messages", { content: "hi" }, (event, data) =>
      received.push({ event, data }),
    );

    expect(received.at(-1)).toEqual({
      event: "error",
      data: { code: "provider_timeout", message: "AI is taking longer than expected." },
    });
  });
});
