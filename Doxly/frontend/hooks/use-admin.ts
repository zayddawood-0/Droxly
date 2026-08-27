import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import {
  getSystemHealth,
  listAdminUsers,
  suspendUser,
  unsuspendUser,
  type AdminUserListParams,
} from "@/lib/api/admin";

const usersKey = (params: AdminUserListParams) => ["admin", "users", params] as const;

/** FR-ADMIN-001 */
export function useAdminUsersQuery(params: AdminUserListParams) {
  return useQuery({
    queryKey: usersKey(params),
    queryFn: () => listAdminUsers(params),
    placeholderData: keepPreviousData,
  });
}

/** FR-ADMIN-002 */
export function useSystemHealthQuery() {
  return useQuery({
    queryKey: ["admin", "system", "health"],
    queryFn: getSystemHealth,
  });
}

/** FR-ADMIN-003 — invalidates the user list so the table's status column
 * reflects the change on the next fetch (ui-ux.md §15's "immediately
 * reflects the user's new status in the table"). */
export function useSuspendUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; reason: string }) =>
      suspendUser(input.id, input.reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

/** FR-ADMIN-003 */
export function useUnsuspendUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unsuspendUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}
