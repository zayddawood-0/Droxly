import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Extraction results" };

export default async function ExtractionResultsPage({
  params,
}: {
  params: Promise<{ extractionId: string }>;
}) {
  const { extractionId } = await params;

  return (
    <>
      <PageHeader
        title="Extraction results"
        description={`Extraction ${extractionId}`}
      />
      <PhasePlaceholder
        phase="Phase 11 — Extraction"
        requirements="FR-EXT-001, FR-EXT-003, FR-EXT-004"
      />
    </>
  );
}
