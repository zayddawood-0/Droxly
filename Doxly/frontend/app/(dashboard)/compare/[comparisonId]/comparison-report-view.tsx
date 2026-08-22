"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Clock, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChangeSummaryStrip, type SummaryFilter } from "@/components/domain/comparisons/change-summary-strip";
import { DiffView } from "@/components/domain/comparisons/diff-view";
import { useComparisonQuery, useCreateComparisonMutation } from "@/hooks/use-comparisons";
import { useDocumentQuery } from "@/hooks/use-documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import { isDoxlyApiError } from "@/lib/types/errors";

export function ComparisonReportView({ comparisonId }: { comparisonId: string }) {
  const router = useRouter();
  const query = useComparisonQuery(comparisonId);
  const createMutation = useCreateComparisonMutation();
  const [filter, setFilter] = useState<SummaryFilter>(null);
  const announcedCompletion = useRef(false);

  const documentAQuery = useDocumentQuery(query.data?.document_a_id ?? "");
  const documentBQuery = useDocumentQuery(query.data?.document_b_id ?? "");

  async function handleRetry() {
    if (!query.data) return;
    try {
      const created = await createMutation.mutateAsync({
        document_a_id: query.data.document_a_id,
        document_b_id: query.data.document_b_id,
      });
      router.push(`/compare/${created.id}`);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't retry this comparison. Please try again.",
      );
    }
  }

  useEffect(() => {
    if (query.data?.status === "completed" && !announcedCompletion.current) {
      toast.success(
        query.data.result?.alignment_quality === "low"
          ? "Comparison complete — documents couldn't be fully aligned"
          : "Comparison complete",
      );
      announcedCompletion.current = true;
    }
  }, [query.data]);

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = isDoxlyApiError(query.error) && query.error.status === 404;
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          {notFound
            ? "This comparison doesn't exist, or you don't have access to it."
            : "We couldn't load this comparison right now."}
        </p>
        <div className="flex gap-2">
          {!notFound && (
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Try again
            </Button>
          )}
          <Button variant="outline" size="sm" render={<Link href="/compare" />} nativeButton={false}>
            Back to Compare
          </Button>
        </div>
      </div>
    );
  }

  const comparison = query.data;

  if (comparison.status === "processing") {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center"
        aria-live="polite"
      >
        <Clock className="size-6 animate-pulse text-info" aria-hidden="true" />
        <p className="text-sm font-medium">Comparing your documents…</p>
        <p className="text-xs text-muted-foreground">
          This usually takes under a minute — feel free to check back.
        </p>
      </div>
    );
  }

  if (comparison.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-16 text-center">
        <p className="text-sm text-danger">This comparison couldn&apos;t be completed.</p>
        <Button variant="outline" size="sm" onClick={handleRetry} disabled={createMutation.isPending}>
          {createMutation.isPending && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          Retry
        </Button>
      </div>
    );
  }

  const result = comparison.result;
  if (!result) return null;

  const aName = documentAQuery.data?.file_name ?? "Document A";
  const bName = documentBQuery.data?.file_name ?? "Document B";

  return (
    <div className="flex flex-col gap-4">
      <p className="truncate text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{aName}</span> vs.{" "}
        <span className="font-medium text-foreground">{bName}</span>
      </p>

      {result.alignment_quality === "low" ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-warning/40 bg-warning-soft/40 px-4 py-5">
          <p className="text-sm text-warning">
            {result.message ?? "These documents are too structurally different for a meaningful comparison."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" render={<Link href={`/documents/${comparison.document_a_id}`} />} nativeButton={false}>
              View {aName}
            </Button>
            <Button variant="outline" size="sm" render={<Link href={`/documents/${comparison.document_b_id}`} />} nativeButton={false}>
              View {bName}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <ChangeSummaryStrip result={result} filter={filter} onFilterChange={setFilter} />
          <DiffView
            result={result}
            documentAId={comparison.document_a_id}
            documentBId={comparison.document_b_id}
            filter={filter}
          />
        </>
      )}
    </div>
  );
}
