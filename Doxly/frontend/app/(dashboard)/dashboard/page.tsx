import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your documents, quick actions, and usage at a glance."
      />
      <PhasePlaceholder
        phase="Phase 4 — Document Management"
        requirements="FR-DOC-001, FR-AI-001, FR-SEARCH-001"
      />
    </>
  );
}
