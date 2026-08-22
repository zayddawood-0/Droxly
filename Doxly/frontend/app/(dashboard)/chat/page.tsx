import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "AI Chat" };

export default function ChatPage() {
  return (
    <>
      <PageHeader
        title="AI Chat"
        description="Ask questions about your documents — grounded, cited, never a guess."
      />
      <PhasePlaceholder
        phase="Phase 9 — AI Chat"
        requirements="FR-AI-001, FR-AI-003, FR-RAG-002"
      />
    </>
  );
}
