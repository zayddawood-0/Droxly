import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { SearchView } from "./search-view";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <>
      <PageHeader
        title="Search"
        description="Find content across your entire document library."
      />
      <Suspense fallback={null}>
        <SearchView />
      </Suspense>
    </>
  );
}
