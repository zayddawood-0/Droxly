import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Admin — System Health" };

export default function AdminSystemPage() {
  return (
    <>
      <PageHeader
        title="System health"
        description="Aggregate processing queue depth, failure rates, AI request volume."
      />
      <PhasePlaceholder
        phase="Phase 2 / 4, hardened in 15"
        requirements="FR-ADMIN-002"
      />
    </>
  );
}
