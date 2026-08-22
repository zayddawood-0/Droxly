import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { ChatView } from "./chat-view";

export const metadata: Metadata = { title: "AI Chat" };

export default function ChatPage() {
  return (
    <>
      <PageHeader
        title="AI Chat"
        description="Ask questions about your documents — grounded, cited, never a guess."
      />
      <ChatView conversationId={null} />
    </>
  );
}
