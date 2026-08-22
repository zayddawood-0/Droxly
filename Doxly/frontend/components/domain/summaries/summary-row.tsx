"use client";

import { useState } from "react";
import { ChevronDown, CircleX, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSummaryQuery } from "@/hooks/use-summaries";
import type { SummaryListItem, SummaryType } from "@/lib/api/summaries";

const TYPE_LABEL: Record<SummaryType, string> = {
  brief: "Brief",
  detailed: "Detailed",
  bullet_points: "Bullet points",
};

/**
 * ui-ux.md §9 — one list entry; clicking expands it "inline, never
 * navigating away from the dialog." Starts expanded when freshly created
 * (`defaultExpanded`) so the user sees their own request begin processing
 * without an extra click.
 */
export function SummaryRow({
  summary,
  defaultExpanded,
  onRetry,
}: {
  summary: SummaryListItem;
  defaultExpanded?: boolean;
  onRetry: (type: SummaryType) => void;
}) {
  const [expanded, setExpanded] = useState(Boolean(defaultExpanded));
  const detail = useSummaryQuery(expanded ? summary.id : null);

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-label={`${expanded ? "Collapse" : "Expand"} ${TYPE_LABEL[summary.summary_type]} summary from ${new Date(summary.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="flex items-center gap-2">
          <Badge variant="outline" className="font-normal">
            {TYPE_LABEL[summary.summary_type]}
          </Badge>
          {summary.status === "processing" && (
            <Loader2 className="size-3.5 animate-spin text-info" aria-hidden="true" />
          )}
          {summary.status === "failed" && (
            <CircleX className="size-3.5 text-danger" aria-hidden="true" />
          )}
          <span className="text-xs text-muted-foreground tabular-nums">
            {new Date(summary.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          </span>
        </span>
        <ChevronDown
          className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")}
          aria-hidden="true"
        />
      </button>

      {expanded && (
        <div className="border-t border-border px-3 py-3 text-sm">
          {detail.isPending ? (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              Loading…
            </p>
          ) : detail.isError ? (
            <p className="text-muted-foreground">Couldn&apos;t load this summary right now.</p>
          ) : detail.data.status === "processing" ? (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              Generating your summary — this can take a moment.
            </p>
          ) : detail.data.status === "failed" ? (
            <div className="flex flex-col items-start gap-2">
              <p className="text-danger">This summary couldn&apos;t be generated.</p>
              <Button variant="outline" size="sm" onClick={() => onRetry(summary.summary_type)}>
                Retry
              </Button>
            </div>
          ) : summary.summary_type === "bullet_points" ? (
            <ul className="list-disc space-y-1 pl-4 text-foreground">
              {(detail.data.content ?? "")
                .split("\n")
                .map((line) => line.replace(/^[-•]\s*/, "").trim())
                .filter(Boolean)
                .map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
            </ul>
          ) : (
            <p className="whitespace-pre-wrap text-foreground">{detail.data.content}</p>
          )}
        </div>
      )}
    </div>
  );
}
