"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createConversation,
  regenerateMessage,
  sendMessage,
  stopMessage,
  type ChatMessage,
  type MessageCitation,
} from "@/lib/api/chat";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

type DraftStatus = "streaming" | "done" | "error" | "stopped";

export type DraftMessage = {
  clientId: string;
  role: "assistant";
  content: string;
  citations: MessageCitation[];
  status: DraftStatus;
  errorMessage?: string;
};

/**
 * Orchestrates FR-AI-001/003/005/006's send → stream → persist flow
 * (architecture.md §5, api.md §4). Server-persisted messages live in
 * TanStack Query's cache (useConversationQuery); this hook layers the
 * in-flight optimistic user bubble + streaming assistant draft on top,
 * then invalidates the conversation query on completion so the server's
 * authoritative row (real ID, citations, content) replaces the draft —
 * one source of truth once a turn finishes, not two permanently.
 */
export function useChatStream(
  conversationId: string | null,
  documentIds: string[] | undefined,
) {
  const queryClient = useQueryClient();
  const [optimisticUserMessage, setOptimisticUserMessage] = useState<ChatMessage | null>(null);
  const [draft, setDraft] = useState<DraftMessage | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const userMessageIdRef = useRef<string | null>(null);
  const lastContentRef = useRef<string>("");

  const finish = useCallback(
    async (targetConversationId: string) => {
      await queryClient.invalidateQueries({ queryKey: ["conversations", "detail", targetConversationId] });
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setOptimisticUserMessage(null);
      setDraft(null);
    },
    [queryClient],
  );

  const runStream = useCallback(
    async (
      targetConversationId: string,
      streamCall: (
        onEvent: Parameters<typeof sendMessage>[2],
        signal: AbortSignal,
      ) => Promise<void>,
    ) => {
      const controller = new AbortController();
      abortRef.current = controller;
      // Mirrors the draft's terminal status without waiting on a
      // (possibly-batched) setState read — decides below whether the turn
      // actually finished cleanly, since a mid-stream `error` event
      // resolves streamCall() without throwing (api.md: it's data the
      // caller interprets, not a transport failure) and must NOT be
      // followed by finish()'s cache-invalidate/clear, which would wipe
      // the error state we just showed the user.
      const terminalStatus: { current: DraftStatus } = { current: "streaming" };

      setDraft({ clientId: crypto.randomUUID(), role: "assistant", content: "", citations: [], status: "streaming" });

      try {
        await streamCall((event) => {
          switch (event.type) {
            case "message_id":
              userMessageIdRef.current = event.messageId;
              break;
            case "token":
              setDraft((prev) =>
                prev ? { ...prev, content: prev.content + event.text } : prev,
              );
              break;
            case "citations":
              setDraft((prev) => (prev ? { ...prev, citations: event.citations } : prev));
              break;
            case "done":
              terminalStatus.current = "done";
              setDraft((prev) => (prev ? { ...prev, status: "done" } : prev));
              break;
            case "error":
              terminalStatus.current = "error";
              setDraft((prev) =>
                prev ? { ...prev, status: "error", errorMessage: event.message } : prev,
              );
              break;
          }
        }, controller.signal);

        if (terminalStatus.current === "done") {
          await finish(targetConversationId);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          setDraft((prev) => (prev ? { ...prev, status: "stopped" } : prev));
          return;
        }
        setDraft((prev) =>
          prev
            ? {
                ...prev,
                status: "error",
                errorMessage: isConnectivityError(error)
                  ? CONNECTIVITY_ERROR_MESSAGE
                  : "Something went wrong generating a response.",
              }
            : prev,
        );
      } finally {
        abortRef.current = null;
      }
    },
    [finish],
  );

  const send = useCallback(
    async (content: string) => {
      lastContentRef.current = content;
      let targetConversationId = conversationId;

      if (!targetConversationId) {
        const created = await createConversation({ document_ids: documentIds });
        targetConversationId = created.id;
      }

      setOptimisticUserMessage({
        id: `local-${Date.now()}`,
        role: "user",
        content,
        citations: [],
        created_at: new Date().toISOString(),
      });

      await runStream(targetConversationId, (onEvent, signal) =>
        sendMessage(targetConversationId as string, content, onEvent, signal),
      );

      return targetConversationId;
    },
    [conversationId, documentIds, runStream],
  );

  const regenerate = useCallback(
    async (messageId: string) => {
      if (!conversationId) return;
      await runStream(conversationId, (onEvent, signal) =>
        regenerateMessage(conversationId, messageId, onEvent, signal),
      );
    },
    [conversationId, runStream],
  );

  const retry = useCallback(async () => {
    if (lastContentRef.current) await send(lastContentRef.current);
  }, [send]);

  const stop = useCallback(async () => {
    abortRef.current?.abort();
    if (conversationId && userMessageIdRef.current) {
      try {
        await stopMessage(conversationId, userMessageIdRef.current);
      } catch {
        // The local abort already stopped the UI from waiting further;
        // a failure to notify the backend isn't itself user-facing here.
      }
    }
  }, [conversationId]);

  return {
    optimisticUserMessage,
    draft,
    isStreaming: draft?.status === "streaming",
    send,
    regenerate,
    retry,
    stop,
  };
}
