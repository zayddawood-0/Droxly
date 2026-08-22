"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowLeftRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentPicker } from "@/components/domain/documents/document-picker";
import { useDocumentsQuery } from "@/hooks/use-documents";
import { useComparisonsQuery, useCreateComparisonMutation } from "@/hooks/use-comparisons";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

/**
 * ui-ux.md §11 — "Document A / Document B picker ... above a past
 * comparisons list ... → report view." No dedicated document context is
 * required to arrive here; the Document Viewer's "Compare" action
 * pre-fills Document A via `?document_a=`.
 */
export function CompareView() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [documentAId, setDocumentAId] = useState<string | null>(searchParams.get("document_a"));
  const [documentBId, setDocumentBId] = useState<string | null>(null);

  const documentsQuery = useDocumentsQuery({ status: "ready", limit: 100 });
  const historyQuery = useComparisonsQuery();
  const createMutation = useCreateComparisonMutation();

  function fileName(id: string) {
    return documentsQuery.data?.items.find((d) => d.id === id)?.file_name ?? "Document";
  }

  async function handleRun() {
    if (!documentAId || !documentBId) return;
    try {
      const created = await createMutation.mutateAsync({
        document_a_id: documentAId,
        document_b_id: documentBId,
      });
      router.push(`/compare/${created.id}`);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't start this comparison. Please try again.",
      );
    }
  }

  const canRun = Boolean(documentAId && documentBId && documentAId !== documentBId);

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
          <div>
            <p className="mb-1.5 text-xs text-muted-foreground">Document A</p>
            <DocumentPicker
              selectedId={documentAId}
              onChange={setDocumentAId}
              excludeId={documentBId}
              placeholder="Select the first document…"
            />
          </div>
          <ArrowLeftRight
            className="mx-auto hidden size-4 shrink-0 text-muted-foreground sm:block"
            aria-hidden="true"
          />
          <div>
            <p className="mb-1.5 text-xs text-muted-foreground">Document B</p>
            <DocumentPicker
              selectedId={documentBId}
              onChange={setDocumentBId}
              excludeId={documentAId}
              placeholder="Select the second document…"
            />
          </div>
        </div>
        <Button type="button" onClick={handleRun} disabled={!canRun || createMutation.isPending} className="self-start">
          {createMutation.isPending && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          Compare
        </Button>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold">Past comparisons</h2>
        {historyQuery.isPending ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : historyQuery.isError ? (
          <div className="flex items-center justify-between rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
            Couldn&apos;t load past comparisons.
            <Button variant="ghost" size="sm" onClick={() => historyQuery.refetch()}>
              Retry
            </Button>
          </div>
        ) : historyQuery.data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            No comparisons yet — pick two documents above to run one.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {historyQuery.data.items.map((comparison) => (
              <li key={comparison.id}>
                <Link
                  href={`/compare/${comparison.id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm outline-none hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <span className="min-w-0 truncate">
                    {documentsQuery.isPending
                      ? "Loading…"
                      : `${fileName(comparison.document_a_id)} vs. ${fileName(comparison.document_b_id)}`}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {new Date(comparison.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
