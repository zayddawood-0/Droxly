"use client";

import { useState } from "react";
import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ConversationList } from "@/components/domain/chat/conversation-list";
import { ChatThread } from "@/components/domain/chat/chat-thread";

/**
 * ui-ux.md §8's two-pane layout. Responsive behavior: "Conversation list
 * becomes a slide-over drawer on mobile (thread is the primary view)."
 */
export function ChatView({ conversationId }: { conversationId: string | null }) {
  const [mobileListOpen, setMobileListOpen] = useState(false);

  return (
    <Sheet open={mobileListOpen} onOpenChange={setMobileListOpen}>
      {/* Height subtracts the fixed TopBar (3.5rem) + main's vertical
          padding (3rem) + PageHeader's own block height + the gap before
          this container — measured empirically against page-shell.tsx's
          current chrome, so the composer stays pinned to the viewport
          bottom (ui-ux.md §8) instead of letting the whole page scroll. */}
      <div className="flex h-[calc(100dvh-13rem)] overflow-hidden rounded-lg border border-border md:h-[calc(100dvh-11.5rem)]">
        <div className="hidden w-64 shrink-0 border-r border-border md:block">
          <ConversationList activeConversationId={conversationId} />
        </div>

        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border p-2 md:hidden">
            <SheetTrigger
              render={<Button variant="ghost" size="icon-sm" aria-label="Open conversation list" />}
            >
              <Menu className="size-4" aria-hidden="true" />
            </SheetTrigger>
            <span className="text-sm font-medium">Chat</span>
          </div>
          <ChatThread conversationId={conversationId} />
        </div>
      </div>

      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader className="sr-only">
          <SheetTitle>Conversations</SheetTitle>
        </SheetHeader>
        <ConversationList
          activeConversationId={conversationId}
          onNavigate={() => setMobileListOpen(false)}
        />
      </SheetContent>
    </Sheet>
  );
}
