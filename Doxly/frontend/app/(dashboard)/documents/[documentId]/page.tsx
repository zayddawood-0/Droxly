import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Document" };

export default async function DocumentViewerPage({
  params,
}: {
  params: Promise<{ documentId: string }>;
}) {
  const { documentId } = await params;

  return (
    <>
      <PageHeader
        title="Document viewer"
        description={`Document ${documentId}`}
      />
      <PhasePlaceholder
        phase="Phase 5 — Document Processing"
        requirements="FR-DOC-003, FR-DOC-008, FR-PROC-004"
      />
    </>
  );
}
