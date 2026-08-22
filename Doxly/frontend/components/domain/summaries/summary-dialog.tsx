"use client";

import { useState } from "react";
import { FileOutput, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSummariesQuery, useCreateSummaryMutation } from "@/hooks/use-summaries";
import { SummaryRow } from "@/components/domain/summaries/summary-row";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import type { SummaryType } from "@/lib/api/summaries";

const TYPE_OPTIONS: { value: SummaryType; label: string }[] = [
  { value: "brief", label: "Brief" },
  { value: "detailed", label: "Detailed" },
  { value: "bullet_points", label: "Bullet points" },
];

/**
 * ui-ux.md §9 — a Dialog (not a route), launched from the Document Viewer's
 * action rail and the Documents list row menu. FR-SUM-001/002: past
 * summaries are always listed and never overwritten by a new request.
 */
export function SummaryDialog({
  documentId,
  open,
  onOpenChange,
}: {
  documentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [summaryType, setSummaryType] = useState<SummaryType>("brief");
  const [freshestId, setFreshestId] = useState<string | null>(null);
  const query = useSummariesQuery(documentId, { enabled: open });
  const createMutation = useCreateSummaryMutation(documentId);

  async function handleGenerate(type: SummaryType) {
    try {
      const created = await createMutation.mutateAsync(type);
      setFreshestId(created.id);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't start generating a summary. Please try again.",
      );
    }
  }

  const hasSummaries = (query.data?.items.length ?? 0) > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Summaries</DialogTitle>
          <DialogDescription>
            Generate a summary at the length you need — every past summary stays available.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label htmlFor="summary-type" className="mb-1 block text-xs font-medium text-muted-foreground">
              Summary type
            </label>
            <Select value={summaryType} onValueChange={(value) => setSummaryType((value as SummaryType) ?? "brief")}>
              <SelectTrigger id="summary-type" className="w-full">
                <SelectValue>
                  {(value: SummaryType) => TYPE_OPTIONS.find((o) => o.value === value)?.label ?? "Brief"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            type="button"
            onClick={() => handleGenerate(summaryType)}
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileOutput className="size-4" aria-hidden="true" />
            )}
            Generate
          </Button>
        </div>

        <div className="flex max-h-80 flex-col gap-2 overflow-y-auto" aria-live="polite">
          {query.isPending ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Loading summaries…</p>
          ) : query.isError ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <p className="text-sm text-muted-foreground">Couldn&apos;t load past summaries.</p>
              <Button variant="outline" size="sm" onClick={() => query.refetch()}>
                Try again
              </Button>
            </div>
          ) : !hasSummaries ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No summaries yet — generate one above.
            </p>
          ) : (
            query.data.items.map((summary) => (
              <SummaryRow
                key={summary.id}
                summary={summary}
                defaultExpanded={summary.id === freshestId}
                onRetry={handleGenerate}
              />
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
