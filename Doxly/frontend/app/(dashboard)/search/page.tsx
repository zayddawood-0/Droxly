import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <>
      <PageHeader
        title="Search"
        description="Find content across your entire document library."
      />
      <PhasePlaceholder
        phase="Phase 13 — Global Search"
        requirements="FR-SEARCH-001, FR-SEARCH-002, FR-SEARCH-003"
      />
    </>
  );
}
