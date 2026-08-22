import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MessageCitation } from "@/lib/api/chat";
import { CitationChip } from "@/components/domain/chat/citation-chip";
import { StreamingIndicator } from "@/components/domain/chat/streaming-indicator";

export type DisplayMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: MessageCitation[];
  status: "done" | "streaming" | "error" | "stopped";
  errorMessage?: string;
};

/**
 * ui-ux.md §8 — user vs. assistant variants; the FR-AI-004 "I don't know"
 * response (zero citations on a completed assistant turn) uses a visually
 * distinct muted/outlined style so it's never mistaken for a confident
 * answer; a failed generation is an inline error bubble with Retry, not a
 * lost message.
 */
export function MessageBubble({
  message,
  isLastAssistantMessage,
  onRegenerate,
  onRetry,
}: {
  message: DisplayMessage;
  isLastAssistantMessage?: boolean;
  onRegenerate?: () => void;
  onRetry?: () => void;
}) {
  const isUser = message.role === "user";
  const isDeclined =
    !isUser && message.status === "done" && message.citations.length === 0 && message.content.length > 0;

  if (message.status === "error") {
    return (
      <div className="flex flex-col items-start gap-1.5">
        <div
          role="alert"
          className="max-w-[85%] rounded-2xl rounded-bl-sm border border-danger/30 bg-danger-soft/40 px-4 py-2.5 text-sm text-foreground"
        >
          {message.content || "Something went wrong generating a response."}
          {message.errorMessage && (
            <p className="mt-1 text-xs text-danger">{message.errorMessage}</p>
          )}
        </div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Retry
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-1.5", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap",
          isUser && "rounded-br-sm bg-primary text-primary-foreground",
          !isUser && !isDeclined && "rounded-bl-sm bg-muted text-foreground",
          !isUser && isDeclined && "rounded-bl-sm border border-dashed border-border text-muted-foreground",
          message.status === "stopped" && "opacity-70",
        )}
      >
        {message.content}
        {message.status === "streaming" && <StreamingIndicator />}
      </div>

      {message.status === "stopped" && (
        <p className="text-xs text-muted-foreground">Generation stopped</p>
      )}

      {message.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {message.citations.map((citation, index) => (
            <CitationChip key={`${citation.document_id}-${index}`} citation={citation} index={index} />
          ))}
        </div>
      )}

      {!isUser && message.status === "done" && isLastAssistantMessage && onRegenerate && (
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-muted-foreground" onClick={onRegenerate}>
          <RotateCcw className="size-3.5" aria-hidden="true" />
          Regenerate
        </Button>
      )}
    </div>
  );
}
