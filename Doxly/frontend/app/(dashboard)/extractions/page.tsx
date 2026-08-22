import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { ExtractionsView } from "./extractions-view";

export const metadata: Metadata = { title: "Extractions" };

export default function ExtractionsPage() {
  return (
    <>
      <PageHeader
        title="Extractions"
        description="Turn a document into structured data — presets or a custom schema."
      />
      <Suspense fallback={null}>
        <ExtractionsView />
      </Suspense>
    </>
  );
}
