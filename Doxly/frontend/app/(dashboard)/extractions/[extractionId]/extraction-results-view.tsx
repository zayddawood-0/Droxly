"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Clock, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useExtractionQuery, useCorrectExtractionMutation, useCreateExtractionMutation } from "@/hooks/use-extractions";
import { ExtractionFieldRow } from "@/components/domain/extractions/extraction-field-row";
import { ExtractionFieldCard } from "@/components/domain/extractions/extraction-field-card";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import { isDoxlyApiError } from "@/lib/types/errors";

export function ExtractionResultsView({ extractionId }: { extractionId: string }) {
  const router = useRouter();
  const query = useExtractionQuery(extractionId);
  const correctMutation = useCorrectExtractionMutation(extractionId);
  const createMutation = useCreateExtractionMutation();
  const announcedCompletion = useRef(false);

  useEffect(() => {
    if (query.data?.status === "completed" && !announcedCompletion.current) {
      const found = query.data.result.filter((f) => f.value !== null).length;
      toast.success(`Extraction complete — ${found} of ${query.data.result.length} fields found`);
      announcedCompletion.current = true;
    }
  }, [query.data]);

  async function handleSave(field: string, value: string) {
    try {
      await correctMutation.mutateAsync([{ field, value }]);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't save that correction. Please try again.",
      );
      throw error;
    }
  }

  async function handleRetry() {
    if (!query.data) return;
    try {
      const created = await createMutation.mutateAsync(
        query.data.template_key
          ? { document_id: query.data.document_id, template_key: query.data.template_key }
          : { document_id: query.data.document_id, schema: query.data.schema },
      );
      router.push(`/extractions/${created.id}`);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't retry this extraction. Please try again.",
      );
    }
  }

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = isDoxlyApiError(query.error) && query.error.status === 404;
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          {notFound
            ? "This extraction doesn't exist, or you don't have access to it."
            : "We couldn't load this extraction right now."}
        </p>
        <div className="flex gap-2">
          {!notFound && (
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Try again
            </Button>
          )}
          <Button variant="outline" size="sm" render={<Link href="/extractions" />} nativeButton={false}>
            Back to Extractions
          </Button>
        </div>
      </div>
    );
  }

  const extraction = query.data;

  if (extraction.status === "processing") {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center"
        aria-live="polite"
      >
        <Clock className="size-6 animate-pulse text-info" aria-hidden="true" />
        <p className="text-sm font-medium">Extracting fields from your document…</p>
        <p className="text-xs text-muted-foreground">
          This usually takes under a minute — feel free to check back.
        </p>
      </div>
    );
  }

  if (extraction.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-16 text-center">
        <p className="text-sm text-danger">This extraction couldn&apos;t be completed.</p>
        <Button variant="outline" size="sm" onClick={handleRetry} disabled={createMutation.isPending}>
          {createMutation.isPending && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Source</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {extraction.result.map((field) => (
              <ExtractionFieldRow
                key={field.field}
                field={field}
                onSave={(value) => handleSave(field.field, value)}
              />
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-col gap-3 md:hidden">
        {extraction.result.map((field) => (
          <ExtractionFieldCard
            key={field.field}
            field={field}
            onSave={(value) => handleSave(field.field, value)}
          />
        ))}
      </div>
    </div>
  );
}
