import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { ChatView } from "../chat-view";

export const metadata: Metadata = { title: "Conversation" };

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;

  return (
    <>
      <PageHeader title="Conversation" description="Ask a follow-up — prior turns stay in context." />
      <ChatView conversationId={conversationId} />
    </>
  );
}
