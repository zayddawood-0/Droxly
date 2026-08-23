"use client";

import { CartesianGrid, Line, LineChart as RechartsLineChart, XAxis, YAxis } from "recharts";

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { ChartDataTable } from "@/components/domain/analytics/chart-data-table";
import type { TimeSeriesPoint } from "@/lib/api/analytics";

function formatShortDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const config: ChartConfig = { count: { label: "Count", color: "var(--color-primary)" } };

/**
 * ui-ux.md §13 — "minimal chart components (line/bar — flat, no 3D/gradient
 * decoration)." No fill/gradient/shadow — a single flat stroke. Paired with
 * a visually-hidden ChartDataTable for the accessibility requirement.
 */
export function AnalyticsLineChart({ title, data }: { title: string; data: TimeSeriesPoint[] }) {
  return (
    <div>
      <ChartContainer config={config} className="aspect-auto h-52 w-full" aria-hidden="true">
        <RechartsLineChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
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
          <Line
            dataKey="count"
            type="monotone"
            stroke="var(--color-count)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </RechartsLineChart>
      </ChartContainer>
      <ChartDataTable caption={title} data={data} />
    </div>
  );
}
