import { apiFetch } from "@/lib/api/client";

/** One function per documented endpoint in specs/api.md §9 (/analytics). */

export type AnalyticsPeriod = "7d" | "30d" | "90d";

export type TimeSeriesPoint = { date: string; count: number };
export type FeatureUsage = { feature: string; count: number };

export type AnalyticsDashboard = {
  documents_processed: number;
  documents_over_time: TimeSeriesPoint[];
  ai_requests: number;
  ai_requests_over_time: TimeSeriesPoint[];
  storage_used_bytes: number;
  most_used_features: FeatureUsage[];
};

/** FR-ANALYTICS-001 */
export function getAnalyticsDashboard(period: AnalyticsPeriod) {
  return apiFetch<AnalyticsDashboard>("/analytics/dashboard", { searchParams: { period } });
}
