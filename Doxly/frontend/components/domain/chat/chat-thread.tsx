"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversationQuery } from "@/hooks/use-conversations";
import { useChatStream } from "@/hooks/use-chat-stream";
import { MessageBubble, type DisplayMessage } from "@/components/domain/chat/message-bubble";
import { Composer } from "@/components/domain/chat/composer";
import { DocumentScopePicker } from "@/components/domain/chat/document-scope-picker";
import { EmptyThreadPrompt } from "@/components/domain/chat/empty-thread-prompt";
import { isDoxlyApiError } from "@/lib/types/errors";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import { toast } from "sonner";

/**
 * ui-ux.md §8's active-thread pane: scope picker (new conversation only —
 * scope is fixed once a conversation exists, api.md has no "update scope"
 * endpoint), message list, composer. `conversationId=null` is the "start a
 * new conversation" state.
 */
export function ChatThread({ conversationId }: { conversationId: string | null }) {
  const router = useRouter();
  const [scopeDocumentIds, setScopeDocumentIds] = useState<string[]>([]);
  const query = useConversationQuery(conversationId);
  const stream = useChatStream(conversationId, scopeDocumentIds);
  const scrollRef = useRef<HTMLDivElement>(null);

  // A11y (ui-ux.md §8): the visible pane updates every token, but this
  // hidden live region's text only changes once a turn reaches "done" —
  // computed directly from render state, not copied via an effect, so
  // screen readers are announced to once per completed turn, never per
  // token mid-stream.
  const announcement = stream.draft?.status === "done" ? stream.draft.content : "";

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [query.data?.messages, stream.draft?.content, stream.optimisticUserMessage]);

  async function handleSend(content: string) {
    try {
      const targetId = await stream.send(content);
      if (!conversationId && targetId) router.push(`/chat/${targetId}`);
    } catch (error) {
      // Only createConversation() can throw here (a mid-stream failure is
      // handled inside useChatStream as a draft error state, never a
      // rejection) — most commonly "no conversation yet" against an
      // unreachable backend.
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't start this conversation. Please try again.",
      );
    }
  }

  async function handleRegenerate(messageId: string) {
    try {
      await stream.regenerate(messageId);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't regenerate this response. Please try again.",
      );
    }
  }

  async function handleRetry() {
    try {
      await stream.retry();
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't retry this message. Please try again.",
      );
    }
  }

  if (conversationId && query.isPending) {
    return (
      <div className="flex flex-1 flex-col gap-3 p-4">
        <Skeleton className="h-16 w-2/3 rounded-2xl" />
        <Skeleton className="ml-auto h-10 w-1/2 rounded-2xl" />
        <Skeleton className="h-20 w-3/4 rounded-2xl" />
      </div>
    );
  }

  if (conversationId && query.isError) {
    const notFound = isDoxlyApiError(query.error) && query.error.status === 404;
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm text-muted-foreground">
          {notFound
            ? "This conversation doesn't exist, or you don't have access to it."
            : "We couldn't load this conversation right now."}
        </p>
        {!notFound && (
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            Try again
          </Button>
        )}
      </div>
    );
  }

  const serverMessages: DisplayMessage[] = (query.data?.messages ?? []).map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations,
    status: "done",
  }));

  const liveMessages: DisplayMessage[] = [];
  if (stream.optimisticUserMessage) {
    liveMessages.push({
      id: stream.optimisticUserMessage.id,
      role: "user",
      content: stream.optimisticUserMessage.content,
      citations: [],
      status: "done",
    });
  }
  if (stream.draft) {
    liveMessages.push({
      id: stream.draft.clientId,
      role: "assistant",
      content: stream.draft.content,
      citations: stream.draft.citations,
      status: stream.draft.status,
      errorMessage: stream.draft.errorMessage,
    });
  }

  const messages = [...serverMessages, ...liveMessages];
  const lastAssistantId = [...messages].reverse().find((message) => message.role === "assistant")?.id;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {!conversationId && (
        <div className="border-b border-border p-3">
          <DocumentScopePicker
            selectedIds={scopeDocumentIds}
            onChange={setScopeDocumentIds}
            disabled={stream.isStreaming}
          />
        </div>
      )}

      <div ref={scrollRef} className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <EmptyThreadPrompt onPick={handleSend} />
        ) : (
          messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              isLastAssistantMessage={message.id === lastAssistantId}
              onRegenerate={
                message.role === "assistant" && message.status === "done" && conversationId
                  ? () => handleRegenerate(message.id)
                  : undefined
              }
              onRetry={message.status === "error" ? handleRetry : undefined}
            />
          ))
        )}
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {announcement}
        </div>
      </div>

      <Composer onSend={handleSend} onStop={stream.stop} isStreaming={stream.isStreaming} />
    </div>
  );
}
