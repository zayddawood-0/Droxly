"use client";

import Link from "next/link";
import { MessageSquarePlus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useConversationsQuery, useDeleteConversationMutation } from "@/hooks/use-conversations";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

/**
 * ui-ux.md §8 — "conversation list sidebar... collapsible"; skeleton rows
 * on first load; "No conversations yet" empty state with prompt
 * suggestions instead of a blank sidebar.
 */
export function ConversationList({
  activeConversationId,
  onNavigate,
}: {
  activeConversationId: string | null;
  onNavigate?: () => void;
}) {
  const query = useConversationsQuery({ limit: 50 });
  const deleteMutation = useDeleteConversationMutation();

  async function handleDelete(id: string) {
    try {
      await deleteMutation.mutateAsync(id);
      toast.success("Conversation deleted");
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't delete this conversation. Please try again.",
      );
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border p-3">
        <h2 className="text-sm font-semibold">Conversations</h2>
        <Button
          variant="ghost"
          size="icon-sm"
          render={<Link href="/chat" />}
          nativeButton={false}
          aria-label="New conversation"
          onClick={onNavigate}
        >
          <MessageSquarePlus className="size-4" aria-hidden="true" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {query.isPending ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : query.isError ? (
          <div className="flex flex-col items-center gap-2 px-3 py-8 text-center">
            <p className="text-sm text-muted-foreground">Couldn&apos;t load your conversations.</p>
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Try again
            </Button>
          </div>
        ) : query.data.items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-3 py-10 text-center">
            <Sparkles className="size-6 text-muted-foreground" aria-hidden="true" />
            <p className="text-sm font-medium">No conversations yet</p>
            <p className="text-xs text-muted-foreground">
              Ask a question about one of your documents to get started.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-1">
            {query.data.items.map((conversation) => (
              <li key={conversation.id} className="group/item relative">
                <Link
                  href={`/chat/${conversation.id}`}
                  onClick={onNavigate}
                  className={cn(
                    "block rounded-lg px-3 py-2 pr-8 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    conversation.id === activeConversationId
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-accent/50",
                  )}
                >
                  <span className="block truncate font-medium">
                    {conversation.title ?? "New conversation"}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {conversation.scope_type === "workspace"
                      ? "All documents"
                      : conversation.scope_type === "multi_document"
                        ? `${conversation.document_ids.length} documents`
                        : "1 document"}
                  </span>
                </Link>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Delete conversation "${conversation.title ?? "New conversation"}"`}
                  className="absolute top-1.5 right-1 opacity-0 group-hover/item:opacity-100 focus-visible:opacity-100"
                  onClick={() => handleDelete(conversation.id)}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
