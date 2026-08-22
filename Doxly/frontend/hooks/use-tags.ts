import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createTag, listTags } from "@/lib/api/tags";

export function useTagsQuery() {
  return useQuery({
    queryKey: ["tags"],
    queryFn: listTags,
  });
}

export function useCreateTagMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; color?: string }) => createTag(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });
}
