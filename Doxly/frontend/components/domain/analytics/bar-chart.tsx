"use client";

import { Bar, BarChart as RechartsBarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { ChartDataTable } from "@/components/domain/analytics/chart-data-table";
import type { TimeSeriesPoint } from "@/lib/api/analytics";

function formatShortDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const config: ChartConfig = { count: { label: "Count", color: "var(--color-info)" } };

/**
 * ui-ux.md §13 — "minimal chart components (line/bar — flat, no 3D/gradient
 * decoration)." Solid fill, no gradient, small corner radius consistent
 * with the app's restrained radius scale. Paired with a visually-hidden
 * ChartDataTable for the accessibility requirement.
 */
export function AnalyticsBarChart({ title, data }: { title: string; data: TimeSeriesPoint[] }) {
  return (
    <div>
      <ChartContainer config={config} className="aspect-auto h-52 w-full" aria-hidden="true">
        <RechartsBarChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={28}
            tickFormatter={formatShortDate}
          />
          <YAxis tickLine={false} axisLine={false} width={28} allowDecimals={false} />
          <ChartTooltip
            content={<ChartTooltipContent labelFormatter={(value) => formatShortDate(String(value))} />}
          />
          <Bar dataKey="count" fill="var(--color-count)" radius={4} isAnimationActive={false} />
        </RechartsBarChart>
      </ChartContainer>
      <ChartDataTable caption={title} data={data} />
    </div>
  );
}
