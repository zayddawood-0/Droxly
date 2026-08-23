"use client";

import { useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BarChart3, FileText, HardDrive, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { UsageStrip } from "@/components/domain/documents/usage-strip";
import { StatCard, StatCardSkeleton } from "@/components/domain/analytics/stat-card";
import { PeriodSelector } from "@/components/domain/analytics/period-selector";
import { AnalyticsLineChart } from "@/components/domain/analytics/line-chart";
import { AnalyticsBarChart } from "@/components/domain/analytics/bar-chart";
import { MostUsedFeaturesList } from "@/components/domain/analytics/most-used-features-list";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalyticsDashboardQuery } from "@/hooks/use-analytics";
import { formatBytes } from "@/lib/constants/documents";
import type { AnalyticsPeriod } from "@/lib/api/analytics";

const VALID_PERIODS: AnalyticsPeriod[] = ["7d", "30d", "90d"];

export function AnalyticsView() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const period = useMemo(() => {
    const raw = searchParams.get("period");
    return VALID_PERIODS.includes(raw as AnalyticsPeriod) ? (raw as AnalyticsPeriod) : "30d";
  }, [searchParams]);

  const setPeriod = useCallback(
    (next: AnalyticsPeriod) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("period", next);
      router.replace(`/analytics?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const query = useAnalyticsDashboardQuery(period);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <UsageStrip />
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {query.isPending ? (
        <AnalyticsSkeleton />
      ) : query.isError ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-16 text-center">
          <p className="text-sm text-muted-foreground">We couldn&apos;t load your analytics right now.</p>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            Try again
          </Button>
        </div>
      ) : query.data.documents_processed === 0 && query.data.ai_requests === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-6 py-16 text-center">
          <BarChart3 className="size-6 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm font-medium">Nothing to show yet</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Your usage will appear here once you start uploading and asking questions.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard icon={FileText} label="Documents processed" value={query.data.documents_processed.toLocaleString()} />
            <StatCard icon={HardDrive} label="Storage used" value={formatBytes(query.data.storage_used_bytes)} />
            <StatCard icon={Sparkles} label="AI requests this period" value={query.data.ai_requests.toLocaleString()} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section className="rounded-lg border border-border p-4">
              <h2 className="mb-3 text-sm font-semibold">Documents processed over time</h2>
              <AnalyticsLineChart title="Documents processed over time" data={query.data.documents_over_time} />
            </section>
            <section className="rounded-lg border border-border p-4">
              <h2 className="mb-3 text-sm font-semibold">AI requests over time</h2>
              <AnalyticsBarChart title="AI requests over time" data={query.data.ai_requests_over_time} />
            </section>
          </div>

          {query.data.most_used_features.length > 0 && (
            <section className="rounded-lg border border-border p-4">
              <h2 className="mb-3 text-sm font-semibold">Most-used features</h2>
              <MostUsedFeaturesList features={query.data.most_used_features} />
            </section>
          )}
        </>
      )}
    </div>
  );
}

function AnalyticsSkeleton() {
  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <StatCardSkeleton key={i} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full rounded-lg" />
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    </>
  );
}
