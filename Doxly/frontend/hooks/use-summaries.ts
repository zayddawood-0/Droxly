import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createSummary, getSummary, listSummaries, type SummaryType } from "@/lib/api/summaries";

const summariesKey = (documentId: string) => ["summaries", documentId] as const;
const summaryKey = (id: string) => ["summaries", "detail", id] as const;

export function useSummariesQuery(documentId: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: summariesKey(documentId),
    queryFn: () => listSummaries(documentId, { limit: 20 }),
    enabled: options.enabled ?? true,
  });
}

/**
 * FR-SUM-001 — "polling result view" (the approved frontend plan's own
 * words for this phase): no SSE for summaries, so this hook re-fetches on
 * an interval while the job is still processing and stops the moment it
 * reaches a terminal status.
 */
export function useSummaryQuery(id: string | null) {
  return useQuery({
    queryKey: summaryKey(id ?? ""),
    queryFn: () => getSummary(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 2000 : false),
  });
}

export function useCreateSummaryMutation(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (summaryType: SummaryType) => createSummary(documentId, summaryType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: summariesKey(documentId) });
    },
  });
}
