import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Analytics" };

export default function AnalyticsPage() {
  return (
    <>
      <PageHeader
        title="Analytics"
        description="What you've processed and asked, over time."
      />
      <PhasePlaceholder
        phase="Phase 14 — Analytics"
        requirements="FR-ANALYTICS-001"
      />
    </>
  );
}
