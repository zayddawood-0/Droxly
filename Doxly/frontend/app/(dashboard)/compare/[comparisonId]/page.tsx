import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { ComparisonReportView } from "./comparison-report-view";

export const metadata: Metadata = { title: "Comparison report" };

export default async function ComparisonReportPage({
  params,
}: {
  params: Promise<{ comparisonId: string }>;
}) {
  const { comparisonId } = await params;

  return (
    <>
      <PageHeader title="Comparison report" description="Additions, deletions, and modifications between the two documents." />
      <ComparisonReportView comparisonId={comparisonId} />
    </>
  );
}
