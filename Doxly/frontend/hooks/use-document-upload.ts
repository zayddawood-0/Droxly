import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { confirmUpload, presignUpload } from "@/lib/api/documents";
import { putFileWithProgress } from "@/lib/api/upload-transport";
import { validateFileForUpload } from "@/lib/validation/upload";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import { isDoxlyApiError } from "@/lib/types/errors";

export type UploadItem = {
  clientId: string;
  file: File;
  status: "uploading" | "confirming" | "done" | "error";
  progress: number;
  error?: string;
  documentId?: string;
};

/**
 * Orchestrates FR-DOC-001's 3-step flow (specs/architecture.md §4):
 * presign → direct-to-storage PUT → confirm. One file's failure never
 * blocks the others (ui-ux.md §6) — each item's state is independent.
 */
export function useDocumentUpload() {
  const [items, setItems] = useState<UploadItem[]>([]);
  const queryClient = useQueryClient();

  const update = useCallback((clientId: string, patch: Partial<UploadItem>) => {
    setItems((prev) =>
      prev.map((item) => (item.clientId === clientId ? { ...item, ...patch } : item)),
    );
  }, []);

  const runUpload = useCallback(
    async (clientId: string, file: File) => {
      try {
        update(clientId, { status: "uploading", progress: 0, error: undefined });

        const presigned = await presignUpload({
          file_name: file.name,
          mime_type: file.type,
          size_bytes: file.size,
        });
        update(clientId, { documentId: presigned.document_id });

        await putFileWithProgress(
          presigned.upload_url,
          file,
          presigned.upload_headers,
          (percent) => update(clientId, { progress: percent }),
        );

        update(clientId, { status: "confirming" });
        await confirmUpload(presigned.document_id);

        update(clientId, { status: "done", progress: 100 });
        queryClient.invalidateQueries({ queryKey: ["documents"] });
      } catch (error) {
        const message = isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : isDoxlyApiError(error) && error.code === "quota_exceeded"
            ? "This file would exceed your storage quota."
            : isDoxlyApiError(error) && error.code === "unsupported_mime_type"
              ? "Unsupported file type."
              : "Upload failed. Please try again.";
        update(clientId, { status: "error", error: message });
      }
    },
    [queryClient, update],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      const accepted: UploadItem[] = [];
      const rejected: UploadItem[] = [];

      for (const file of files) {
        // Avoid crypto.randomUUID(): it requires a secure context (HTTPS/
        // localhost) in real browsers and isn't guaranteed in every test
        // environment either — this only needs to be unique within one
        // upload batch, not cryptographically random.
        const clientId = `${file.name}-${file.size}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const validationError = validateFileForUpload(file);
        if (validationError) {
          rejected.push({
            clientId,
            file,
            status: "error",
            progress: 0,
            error: validationError,
          });
        } else {
          accepted.push({ clientId, file, status: "uploading", progress: 0 });
        }
      }

      setItems((prev) => [...prev, ...rejected, ...accepted]);
      for (const item of accepted) {
        void runUpload(item.clientId, item.file);
      }
    },
    [runUpload],
  );

  const retry = useCallback(
    (clientId: string) => {
      const item = items.find((i) => i.clientId === clientId);
      if (item) void runUpload(clientId, item.file);
    },
    [items, runUpload],
  );

  const remove = useCallback((clientId: string) => {
    setItems((prev) => prev.filter((item) => item.clientId !== clientId));
  }, []);

  const reset = useCallback(() => setItems([]), []);

  return { items, addFiles, retry, remove, reset };
}
