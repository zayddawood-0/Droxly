import { useQuery } from "@tanstack/react-query";

import { getUsage } from "@/lib/api/users";

export function useUsageQuery() {
  return useQuery({
    queryKey: ["usage"],
    queryFn: getUsage,
  });
}
