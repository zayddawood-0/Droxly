import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { search, type SearchParams } from "@/lib/api/search";

/** FR-SEARCH-001 — only fires once there's a non-empty, debounced query. */
export function useSearchQuery(params: SearchParams) {
  return useQuery({
    queryKey: ["search", params],
    queryFn: () => search(params),
    enabled: params.q.trim().length > 0,
    placeholderData: keepPreviousData,
  });
}
