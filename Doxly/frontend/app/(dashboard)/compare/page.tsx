import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { CompareView } from "./compare-view";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return (
    <>
      <PageHeader
        title="Compare"
        description="See exactly what changed between two documents."
      />
      <Suspense fallback={null}>
        <CompareView />
      </Suspense>
    </>
  );
}
