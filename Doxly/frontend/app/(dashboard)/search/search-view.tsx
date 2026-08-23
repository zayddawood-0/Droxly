"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search as SearchIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SearchInput } from "@/components/domain/search/search-input";
import { FilterBar, type SearchFilters } from "@/components/domain/search/filter-bar";
import { ResultCard, groupResultsByDocument } from "@/components/domain/search/result-card";
import { useSearchQuery } from "@/hooks/use-search";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import type { DocumentStatus } from "@/lib/api/documents";

const PAGE_SIZE = 20;
const DEBOUNCE_MS = 400;

const EXAMPLE_QUERIES = ["termination clause", "Q3 revenue", "invoice total", "project deadline"];

function readFilters(params: URLSearchParams): SearchFilters {
  return {
    mimeType: params.get("type") ?? "all",
    tagId: params.get("tag") ?? "all",
    status: (params.get("status") as DocumentStatus | null) ?? "all",
    dateFrom: params.get("from") ?? "",
    dateTo: params.get("to") ?? "",
  };
}

export function SearchView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const page = Number(searchParams.get("page") ?? "0");

  const [queryInput, setQueryInput] = useState(searchParams.get("q") ?? "");
  const debouncedQuery = useDebouncedValue(queryInput, DEBOUNCE_MS);

  const updateUrl = useCallback(
    (patch: Partial<SearchFilters> & { q?: string; page?: number }) => {
      const next = new URLSearchParams(searchParams.toString());
      const merged = { ...filters, q: searchParams.get("q") ?? "", ...patch };

      if (merged.q) next.set("q", merged.q);
      else next.delete("q");
      if (merged.mimeType !== "all") next.set("type", merged.mimeType);
      else next.delete("type");
      if (merged.tagId !== "all") next.set("tag", merged.tagId);
      else next.delete("tag");
      if (merged.status !== "all") next.set("status", merged.status);
      else next.delete("status");
      if (merged.dateFrom) next.set("from", merged.dateFrom);
      else next.delete("from");
      if (merged.dateTo) next.set("to", merged.dateTo);
      else next.delete("to");

      if (patch.page !== undefined) next.set("page", String(patch.page));
      else next.delete("page");

      router.replace(`/search?${next.toString()}`, { scroll: false });
    },
    [filters, router, searchParams],
  );

  // Keep the URL in sync once the debounce settles, so the search is
  // shareable/bookmarkable (route table: "/search: ... URL state").
  useEffect(() => {
    if (debouncedQuery !== (searchParams.get("q") ?? "")) {
      updateUrl({ q: debouncedQuery, page: undefined });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery]);

  function updateFilters(patch: Partial<SearchFilters>) {
    updateUrl({ ...patch, page: undefined });
  }

  const invalidDateRange =
    filters.dateFrom !== "" && filters.dateTo !== "" && filters.dateFrom > filters.dateTo;

  const trimmedQuery = debouncedQuery.trim();
  const hasQuery = trimmedQuery.length > 0;

  const query = useSearchQuery({
    q: hasQuery && !invalidDateRange ? trimmedQuery : "",
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    mime_type: filters.mimeType === "all" ? undefined : filters.mimeType,
    tag_id: filters.tagId === "all" ? undefined : filters.tagId,
    status: filters.status === "all" ? undefined : filters.status,
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
  });

  const isSettling = queryInput !== debouncedQuery;
  const grouped = query.data ? groupResultsByDocument(query.data.items) : [];
  const totalPages = query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0;

  return (
    <div className="flex flex-col gap-4">
      <SearchInput
        value={queryInput}
        onChange={setQueryInput}
        loading={isSettling || (hasQuery && query.isFetching)}
        autoFocus
      />

      {hasQuery && <FilterBar filters={filters} onChange={updateFilters} />}

      <p role="status" aria-live="polite" className="sr-only">
        {hasQuery && query.data
          ? `${query.data.total} result${query.data.total === 1 ? "" : "s"} for "${trimmedQuery}"`
          : ""}
      </p>

      {!hasQuery ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
          <SearchIcon className="size-6 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm font-medium">Search across all your documents</p>
          <div className="flex flex-wrap justify-center gap-2">
            {EXAMPLE_QUERIES.map((example) => (
              <Button key={example} variant="outline" size="sm" onClick={() => setQueryInput(example)}>
                {example}
              </Button>
            ))}
          </div>
        </div>
      ) : invalidDateRange ? (
        <p className="rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-4 py-6 text-center text-sm text-danger">
          The &ldquo;From&rdquo; date must be before the &ldquo;To&rdquo; date.
        </p>
      ) : query.isPending ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : query.isError ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-12 text-center">
          <p className="text-sm text-muted-foreground">We couldn&apos;t load results right now.</p>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            Try again
          </Button>
        </div>
      ) : grouped.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-6 py-16 text-center text-sm text-muted-foreground">
          No results for &ldquo;{trimmedQuery}&rdquo; — try different terms or check your filters.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {grouped.map((result) => (
              <ResultCard key={result.document_id} result={result} />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => updateUrl({ page: page - 1 })}
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
                onClick={() => updateUrl({ page: page + 1 })}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
