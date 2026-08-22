import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return (
    <>
      <PageHeader
        title="Compare"
        description="See exactly what changed between two documents."
      />
      <PhasePlaceholder
        phase="Phase 12 — Comparison"
        requirements="FR-COMP-001, FR-COMP-003"
      />
    </>
  );
}
