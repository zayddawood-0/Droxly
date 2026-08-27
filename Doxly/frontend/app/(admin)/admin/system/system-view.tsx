"use client";

import { ListChecks, AlertTriangle, Bot, ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { StatCard, StatCardSkeleton } from "@/components/domain/analytics/stat-card";
import { Button } from "@/components/ui/button";
import { useSystemHealthQuery } from "@/hooks/use-admin";

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}

/** ui-ux.md §15 — "StatCard/Table for queue depth and failure-rate metrics." */
export function AdminSystemView() {
  const query = useSystemHealthQuery();

  return (
    <>
      <PageHeader
        title="System health"
        description="Aggregate processing queue depth, failure rates, AI request volume."
      />

      {query.isPending ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
      ) : query.isError ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-16 text-center">
          <p className="text-sm text-muted-foreground">
            We couldn&apos;t load system health right now.
          </p>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={ListChecks} label="Queue depth" value={String(query.data.queue_depth)} />
          <StatCard
            icon={AlertTriangle}
            label="Processing failure rate (24h)"
            value={formatPercent(query.data.processing_failure_rate_24h)}
          />
          <StatCard icon={Bot} label="AI requests (24h)" value={String(query.data.ai_requests_24h)} />
          <StatCard
            icon={ShieldAlert}
            label="AI error rate (24h)"
            value={formatPercent(query.data.ai_error_rate_24h)}
          />
        </div>
      )}
    </>
  );
}
