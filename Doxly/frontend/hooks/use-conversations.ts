import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
} from "@/lib/api/chat";

const conversationsKey = (params: { limit?: number; offset?: number } = {}) =>
  ["conversations", params] as const;
const conversationKey = (id: string) => ["conversations", "detail", id] as const;

export function useConversationsQuery(params: { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: conversationsKey(params),
    queryFn: () => listConversations(params),
  });
}

export function useConversationQuery(id: string | null) {
  return useQuery({
    queryKey: conversationKey(id ?? ""),
    queryFn: () => getConversation(id as string),
    enabled: id !== null,
  });
}

export function useCreateConversationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { document_ids?: string[] }) => createConversation(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}

export function useDeleteConversationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
