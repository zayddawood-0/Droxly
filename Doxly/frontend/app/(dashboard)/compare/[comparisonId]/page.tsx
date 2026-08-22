import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Comparison report" };

export default async function ComparisonReportPage({
  params,
}: {
  params: Promise<{ comparisonId: string }>;
}) {
  const { comparisonId } = await params;

  return (
    <>
      <PageHeader
        title="Comparison report"
        description={`Comparison ${comparisonId}`}
      />
      <PhasePlaceholder
        phase="Phase 12 — Comparison"
        requirements="FR-COMP-002, FR-COMP-003"
      />
    </>
  );
}
