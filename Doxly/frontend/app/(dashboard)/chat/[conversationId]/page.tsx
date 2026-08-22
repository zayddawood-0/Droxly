import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Conversation" };

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;

  return (
    <>
      <PageHeader title="Conversation" description={`Thread ${conversationId}`} />
      <PhasePlaceholder
        phase="Phase 9 — AI Chat"
        requirements="FR-AI-001, FR-AI-005, FR-AI-006"
      />
    </>
  );
}
