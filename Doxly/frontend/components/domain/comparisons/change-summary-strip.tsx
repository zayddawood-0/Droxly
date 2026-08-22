"use client";

import { cn } from "@/lib/utils";
import { ChangeTypeBadge, type ChangeBadgeKind } from "@/components/domain/comparisons/change-type-badge";
import type { ComparisonResult } from "@/lib/api/comparisons";

export type SummaryFilter = "addition" | "deletion" | "modification" | null;

/**
 * ui-ux.md §11 — "a change-summary strip (counts by type)"; "report
 * supports filtering by change type." Each chip is a toggle: selecting one
 * filters DiffView down to that category, selecting it again clears the
 * filter.
 */
export function ChangeSummaryStrip({
  result,
  filter,
  onFilterChange,
}: {
  result: ComparisonResult;
  filter: SummaryFilter;
  onFilterChange: (next: SummaryFilter) => void;
}) {
  const counts: { kind: ChangeBadgeKind; filterValue: NonNullable<SummaryFilter>; count: number }[] = [
    { kind: "addition", filterValue: "addition", count: result.additions.length },
    { kind: "deletion", filterValue: "deletion", count: result.deletions.length },
    { kind: "modification", filterValue: "modification", count: result.modifications.length },
  ];

  return (
    <div
      role="group"
      aria-label="Filter changes by type"
      className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2.5"
    >
      {counts.map(({ kind, filterValue, count }) => {
        const active = filter === filterValue;
        return (
          <button
            key={kind}
            type="button"
            aria-pressed={active}
            onClick={() => onFilterChange(active ? null : filterValue)}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-1 py-0.5 text-sm outline-none transition-opacity focus-visible:ring-3 focus-visible:ring-ring/50",
              !active && filter !== null && "opacity-50",
            )}
          >
            <ChangeTypeBadge kind={kind} />
            <span className="tabular-nums text-muted-foreground">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
