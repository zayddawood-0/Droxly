import { Loader2, CircleCheck, CircleX, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DocumentStatus } from "@/lib/api/documents";

export const STAGE_LABEL: Record<DocumentStatus, string> = {
  queued: "Queued",
  extracting: "Extracting",
  chunking: "Chunking",
  embedding: "Embedding",
  ready: "Ready",
  failed: "Failed",
};

const IN_PROGRESS_STATUSES: DocumentStatus[] = ["extracting", "chunking", "embedding"];

/**
 * The one shared status-badge vocabulary (specs/ui-ux.md "Processing
 * Indicators") — used identically on Documents list/table/grid, the
 * Document Viewer, and (later) every document picker. No page invents its
 * own status styling. `variant="compact"` collapses the three in-progress
 * stages into a single pulsing "Processing" label with the specific stage
 * in a tooltip, for tight spaces (table rows); `variant="full"` (default)
 * always shows the exact stage.
 */
export function StatusBadge({
  status,
  processingError,
  variant = "full",
  className,
}: {
  status: DocumentStatus;
  processingError?: string | null;
  variant?: "full" | "compact";
  className?: string;
}) {
  const inProgress = IN_PROGRESS_STATUSES.includes(status);
  const label =
    variant === "compact" && inProgress ? "Processing" : STAGE_LABEL[status];

  const badge = (
    <Badge
      className={cn(
        "gap-1.5 font-normal",
        status === "queued" && "bg-muted text-muted-foreground",
        inProgress && "bg-info-soft text-info",
        status === "ready" && "bg-success-soft text-success",
        status === "failed" && "bg-danger-soft text-danger",
        className,
      )}
    >
      {status === "queued" && <Clock className="size-3" aria-hidden="true" />}
      {inProgress && (
        <Loader2 className="size-3 animate-spin" aria-hidden="true" />
      )}
      {status === "ready" && <CircleCheck className="size-3" aria-hidden="true" />}
      {status === "failed" && <CircleX className="size-3" aria-hidden="true" />}
      {label}
    </Badge>
  );

  const tooltipText =
    status === "failed" && processingError
      ? processingError
      : variant === "compact" && inProgress
        ? STAGE_LABEL[status]
        : null;

  if (!tooltipText) return badge;

  return (
    <Tooltip>
      <TooltipTrigger render={<span className="inline-flex" />}>
        {badge}
      </TooltipTrigger>
      <TooltipContent>{tooltipText}</TooltipContent>
    </Tooltip>
  );
}
