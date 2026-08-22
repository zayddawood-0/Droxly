import {
  useMutation,
  useQuery,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";

import {
  deleteDocument,
  getDocument,
  listDocuments,
  reprocessDocument,
  updateDocument,
  type DocumentDetail,
  type DocumentListParams,
} from "@/lib/api/documents";

const documentsKey = (params: DocumentListParams) => ["documents", params] as const;
const documentKey = (id: string) => ["documents", "detail", id] as const;

export function useDocumentsQuery(params: DocumentListParams) {
  return useQuery({
    queryKey: documentsKey(params),
    queryFn: () => listDocuments(params),
    placeholderData: keepPreviousData,
  });
}

export function useDocumentQuery(id: string) {
  return useQuery({
    queryKey: documentKey(id),
    queryFn: () => getDocument(id),
  });
}

export function useUpdateDocumentMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      id: string;
      file_name?: string;
      tag_ids?: string[];
    }) => updateDocument(input.id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocumentMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

/** FR-PROC-005 — "Retry processing" on a `failed` document (ui-ux.md §7). */
export function useReprocessDocumentMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => reprocessDocument(id),
    onSuccess: (result, id) => {
      queryClient.setQueryData(documentKey(id), (prev: DocumentDetail | undefined) =>
        prev ? { ...prev, status: result.status, processing_error: null } : prev,
      );
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
