"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { PageHeader } from "@/components/layout/page-header";
import { DocumentsToolbar, type DocumentsFilters } from "@/components/domain/documents/documents-toolbar";
import { DocumentTable } from "@/components/domain/documents/document-table";
import { DocumentCard } from "@/components/domain/documents/document-card";
import { DocumentsEmptyState } from "@/components/domain/documents/documents-empty-state";
import { UploadDialog } from "@/components/domain/documents/upload-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useDocumentsQuery } from "@/hooks/use-documents";
import type { DocumentStatus } from "@/lib/api/documents";

const PAGE_SIZE = 20;

function readFilters(params: URLSearchParams): DocumentsFilters {
  return {
    search: params.get("search") ?? "",
    status: (params.get("status") as DocumentStatus | null) ?? "all",
    tagId: params.get("tag") ?? "all",
    sort: (params.get("sort") as DocumentsFilters["sort"]) ?? "created_at_desc",
    view: (params.get("view") as DocumentsFilters["view"]) ?? "list",
  };
}

export function DocumentsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const page = Number(searchParams.get("page") ?? "0");

  const [uploadOpen, setUploadOpen] = useState(false);

  const updateFilters = useCallback(
    (patch: Partial<DocumentsFilters> & { page?: number }) => {
      const next = new URLSearchParams(searchParams.toString());
      const merged = { ...filters, ...patch };

      if (merged.search) next.set("search", merged.search);
      else next.delete("search");
      if (merged.status !== "all") next.set("status", merged.status);
      else next.delete("status");
      if (merged.tagId !== "all") next.set("tag", merged.tagId);
      else next.delete("tag");
      next.set("sort", merged.sort);
      next.set("view", merged.view);

      // Any filter change resets pagination — except an explicit page nav.
      if (patch.page !== undefined) next.set("page", String(patch.page));
      else next.delete("page");

      router.replace(`/documents?${next.toString()}`, { scroll: false });
    },
    [filters, router, searchParams],
  );

  const query = useDocumentsQuery({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    status: filters.status === "all" ? undefined : filters.status,
    tag_id: filters.tagId === "all" ? undefined : filters.tagId,
    sort: filters.sort,
  });

  const hasActiveFilters =
    filters.search !== "" || filters.status !== "all" || filters.tagId !== "all";

  const visibleDocuments = useMemo(() => {
    const items = query.data?.items ?? [];
    if (!filters.search) return items;
    const needle = filters.search.toLowerCase();
    return items.filter((doc) => doc.file_name.toLowerCase().includes(needle));
  }, [query.data, filters.search]);

  function clearFilters() {
    updateFilters({ search: "", status: "all", tagId: "all" });
  }

  const totalPages = query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0;

  return (
    <>
      <PageHeader
        title="Documents"
        description="Every document you've uploaded, in one place."
      />

      <DocumentsToolbar
        filters={filters}
        onChange={updateFilters}
        onUpload={() => setUploadOpen(true)}
      />

      <div className="mt-4">
        {query.isPending ? (
          <DocumentsListSkeleton view={filters.view} />
        ) : query.isError ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-16 text-center">
            <p className="text-sm text-muted-foreground">
              We couldn&apos;t load your documents right now.
            </p>
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Try again
            </Button>
          </div>
        ) : query.data.items.length === 0 && !hasActiveFilters ? (
          <DocumentsEmptyState variant="no-documents" onUpload={() => setUploadOpen(true)} />
        ) : visibleDocuments.length === 0 ? (
          <DocumentsEmptyState variant="no-results" onClearFilters={clearFilters} />
        ) : filters.view === "list" ? (
          <>
            <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
              <DocumentTable documents={visibleDocuments} />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:hidden">
              {visibleDocuments.map((doc) => (
                <DocumentCard key={doc.id} document={doc} />
              ))}
            </div>
          </>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visibleDocuments.map((doc) => (
              <DocumentCard key={doc.id} document={doc} />
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => updateFilters({ page: page - 1 })}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground tabular-nums">
              Page {page + 1} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= totalPages}
              onClick={() => updateFilters({ page: page + 1 })}
            >
              Next
            </Button>
          </div>
        )}
      </div>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </>
  );
}

function DocumentsListSkeleton({ view }: { view: "list" | "grid" }) {
  if (view === "grid") {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}
