import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Upload a document" };

// Full-page fallback for direct linking — the primary upload entry point is a
// modal launched from Documents/Dashboard (specs/ui-ux.md §6).
export default function UploadPage() {
  return (
    <>
      <PageHeader
        title="Upload a document"
        description="PDF, DOCX, TXT, or CSV — up to the plan's size limit."
      />
      <PhasePlaceholder
        phase="Phase 4 — Document Management"
        requirements="FR-DOC-001, FR-DOC-008"
      />
    </>
  );
}
