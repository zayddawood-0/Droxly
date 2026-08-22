import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  correctExtraction,
  createExtraction,
  getExtraction,
  listExtractionTemplates,
  listExtractionsForDocument,
  type SchemaField,
} from "@/lib/api/extractions";

const templatesKey = ["extraction-templates"] as const;
const documentExtractionsKey = (documentId: string) => ["extractions", "document", documentId] as const;
const extractionKey = (id: string) => ["extractions", "detail", id] as const;

/** FR-EXT-002 */
export function useExtractionTemplatesQuery() {
  return useQuery({
    queryKey: templatesKey,
    queryFn: listExtractionTemplates,
    staleTime: Infinity, // presets don't change during a session
  });
}

/** FR-EXT-001 — extraction history for one document. */
export function useDocumentExtractionsQuery(documentId: string | null) {
  return useQuery({
    queryKey: documentExtractionsKey(documentId ?? ""),
    queryFn: () => listExtractionsForDocument(documentId as string, { limit: 20 }),
    enabled: documentId !== null,
  });
}

/** FR-EXT-001/003 — "results-pending state" (ui-ux.md §10): polls while processing, stops on any terminal status. */
export function useExtractionQuery(id: string | null) {
  return useQuery({
    queryKey: extractionKey(id ?? ""),
    queryFn: () => getExtraction(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 2000 : false),
  });
}

export function useCreateExtractionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { document_id: string; template_key?: string; schema?: SchemaField[] }) =>
      createExtraction(input),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: documentExtractionsKey(variables.document_id) });
    },
  });
}

/** FR-EXT-004 */
export function useCorrectExtractionMutation(extractionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (corrections: { field: string; value: unknown }[]) =>
      correctExtraction(extractionId, corrections),
    onSuccess: (updated) => {
      queryClient.setQueryData(extractionKey(extractionId), updated);
    },
  });
}
