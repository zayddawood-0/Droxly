import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <>
      <PageHeader
        title="Documents"
        description="Every document you've uploaded, in one place."
        actions={<Button disabled>Upload</Button>}
      />
      <PhasePlaceholder
        phase="Phase 4 — Document Management"
        requirements="FR-DOC-001, FR-DOC-002, FR-DOC-006, FR-DOC-007"
      />
    </>
  );
}
