import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Extractions" };

export default function ExtractionsPage() {
  return (
    <>
      <PageHeader
        title="Extractions"
        description="Turn a document into structured data — presets or a custom schema."
      />
      <PhasePlaceholder
        phase="Phase 11 — Extraction"
        requirements="FR-EXT-001, FR-EXT-002, FR-EXT-003"
      />
    </>
  );
}
