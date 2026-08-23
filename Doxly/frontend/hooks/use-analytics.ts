import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { getAnalyticsDashboard, type AnalyticsPeriod } from "@/lib/api/analytics";

/** FR-ANALYTICS-001 — "period selector re-fetches chart data" (ui-ux.md §13). */
export function useAnalyticsDashboardQuery(period: AnalyticsPeriod) {
  return useQuery({
    queryKey: ["analytics", "dashboard", period],
    queryFn: () => getAnalyticsDashboard(period),
    placeholderData: keepPreviousData,
  });
}
