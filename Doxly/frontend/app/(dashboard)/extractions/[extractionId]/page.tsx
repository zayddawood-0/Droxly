import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { ExtractionResultsView } from "./extraction-results-view";

export const metadata: Metadata = { title: "Extraction results" };

export default async function ExtractionResultsPage({
  params,
}: {
  params: Promise<{ extractionId: string }>;
}) {
  const { extractionId } = await params;

  return (
    <>
      <PageHeader title="Extraction results" description="Field-by-field, with confidence and source." />
      <ExtractionResultsView extractionId={extractionId} />
    </>
  );
}
