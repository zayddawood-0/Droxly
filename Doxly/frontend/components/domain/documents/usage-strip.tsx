"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes } from "@/lib/constants/documents";
import { useUsageQuery } from "@/hooks/use-usage";

/**
 * "Small and unobtrusive" (specs/ui-ux.md §4) — reused from Dashboard on
 * Settings → Plan & Usage. Degrades by disappearing on error rather than a
 * scary error card, matching that framing; this is a nice-to-have strip,
 * not a feature the user is blocked without.
 */
export function UsageStrip() {
  const query = useUsageQuery();

  if (query.isPending) {
    return <Skeleton className="h-5 w-48" />;
  }
  if (query.isError) {
    return null;
  }

  const { storage_used_bytes, storage_quota_bytes, plan } = query.data;
  const percent = Math.min(100, Math.round((storage_used_bytes / storage_quota_bytes) * 100));

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="capitalize">{plan} plan</span>
      <span aria-hidden="true">·</span>
      <span className="tabular-nums">
        {formatBytes(storage_used_bytes)} of {formatBytes(storage_quota_bytes)} used
      </span>
      <div className="h-1 w-24 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${percent}%` }}
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Storage used"
        />
      </div>
    </div>
  );
}
