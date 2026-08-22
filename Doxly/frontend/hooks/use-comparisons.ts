import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createComparison, getComparison, listComparisons } from "@/lib/api/comparisons";

const comparisonsKey = ["comparisons"] as const;
const comparisonKey = (id: string) => ["comparisons", "detail", id] as const;

/** FR-COMP-002 — this user's comparison history, shown on the /compare picker page. */
export function useComparisonsQuery() {
  return useQuery({
    queryKey: comparisonsKey,
    queryFn: () => listComparisons({ limit: 20 }),
  });
}

/** FR-COMP-002/003 — "report-pending state" (ui-ux.md §11): polls while processing, stops on any terminal status. */
export function useComparisonQuery(id: string | null) {
  return useQuery({
    queryKey: comparisonKey(id ?? ""),
    queryFn: () => getComparison(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 2000 : false),
  });
}

export function useCreateComparisonMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { document_a_id: string; document_b_id: string }) => createComparison(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: comparisonsKey });
    },
  });
}
