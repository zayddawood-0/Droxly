import { useQuery } from "@tanstack/react-query";

import { getCurrentUser } from "@/lib/api/users";

/** FR-USER-001 — also the source of truth for the admin role guard (security.md §3.1). */
export function useCurrentUserQuery() {
  return useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
  });
}
