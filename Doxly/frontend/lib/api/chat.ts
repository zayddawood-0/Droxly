import { apiFetch } from "@/lib/api/client";
import { consumeEventStream } from "@/lib/api/sse";

/** One function per documented endpoint in specs/api.md §4 (/chat). */

export type MessageRole = "user" | "assistant";
export type ScopeType = "single_document" | "multi_document" | "workspace";

export type MessageCitation = {
  document_id: string;
  page_number: number | null;
  snippet: string;
  relevance_score: number | null;
};

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  citations: MessageCitation[];
  created_at: string;
};

export type ConversationSummary = {
  id: string;
  title: string | null;
  scope_type: ScopeType;
  document_ids: string[];
  updated_at: string;
};

export type ConversationDetail = ConversationSummary & {
  created_at: string;
  messages: ChatMessage[];
};

export type PaginatedConversations = {
  items: ConversationSummary[];
  total: number;
  limit: number;
  offset: number;
};

/** FR-AI-001, FR-AI-002 */
export function createConversation(input: { document_ids?: string[] }) {
  return apiFetch<ConversationDetail>("/chat/conversations", {
    method: "POST",
    body: input,
  });
}

/** FR-AI-003 */
export function listConversations(params: { limit?: number; offset?: number } = {}) {
  return apiFetch<PaginatedConversations>("/chat/conversations", { searchParams: params });
}

/** FR-AI-003 */
export function getConversation(id: string) {
  return apiFetch<ConversationDetail>(`/chat/conversations/${id}`);
}

/** FR-AI-003 (cleanup) */
export function deleteConversation(id: string) {
  return apiFetch<void>(`/chat/conversations/${id}`, { method: "DELETE" });
}

/**
 * FR-AI-006 — signals the in-flight run for `messageId` to halt; the
 * partial assistant content already streamed is persisted, not discarded.
 */
export function stopMessage(conversationId: string, messageId: string) {
  return apiFetch<{ message_id: string; status: "stopped" }>(
    `/chat/conversations/${conversationId}/messages/${messageId}/stop`,
    { method: "POST" },
  );
}

export type ChatStreamEvent =
  | { type: "message_id"; messageId: string }
  | { type: "token"; text: string }
  | { type: "citations"; citations: MessageCitation[] }
  | { type: "done"; messageId: string }
  | { type: "error"; code: string; message: string };

/**
 * FR-AI-001, FR-AI-003, FR-AI-004, FR-AI-005, FR-RAG-001, FR-RAG-002 —
 * the one streaming chat endpoint (architecture.md §5). `onEvent` receives
 * every SSE event in arrival order; a thrown error means the stream never
 * opened at all (api.md: "errors returned as standard JSON before the
 * stream opens") — callers branch on that with `isConnectivityError`, same
 * as every other endpoint in this app.
 */
export async function sendMessage(
  conversationId: string,
  content: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await consumeEventStream(
    `/chat/conversations/${conversationId}/messages`,
    { content },
    (event, data) => onEvent(toChatStreamEvent(event, data)),
    signal,
  );
}

/** FR-AI-006 — "Regenerate" re-runs the last turn (api.md's regenerate endpoint, added at Phase 9 implementation time to close a spec gap). */
export async function regenerateMessage(
  conversationId: string,
  messageId: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await consumeEventStream(
    `/chat/conversations/${conversationId}/messages/${messageId}/regenerate`,
    undefined,
    (event, data) => onEvent(toChatStreamEvent(event, data)),
    signal,
  );
}

function toChatStreamEvent(event: string, data: unknown): ChatStreamEvent {
  switch (event) {
    case "message_id":
      return { type: "message_id", messageId: (data as { message_id: string }).message_id };
    case "token":
      return { type: "token", text: (data as { text: string }).text };
    case "citations":
      return {
        type: "citations",
        citations: (data as { citations: MessageCitation[] }).citations,
      };
    case "done":
      return { type: "done", messageId: (data as { message_id: string }).message_id };
    case "error": {
      const error = data as { code: string; message: string };
      return { type: "error", code: error.code, message: error.message };
    }
    default:
      return { type: "error", code: "unknown_event", message: `Unrecognized event: ${event}` };
  }
}
