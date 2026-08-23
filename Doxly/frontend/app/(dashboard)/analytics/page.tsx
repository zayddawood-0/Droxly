import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { AnalyticsView } from "./analytics-view";

export const metadata: Metadata = { title: "Analytics" };

export default function AnalyticsPage() {
  return (
    <>
      <PageHeader
        title="Analytics"
        description="What you've processed and asked, over time."
      />
      <Suspense fallback={null}>
        <AnalyticsView />
      </Suspense>
    </>
  );
}
