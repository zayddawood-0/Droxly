"use client";

import { PageHeader } from "@/components/layout/page-header";
import { UploadDropzone } from "@/components/domain/documents/upload-dropzone";
import { UploadFileRow } from "@/components/domain/documents/upload-file-row";
import { useDocumentUpload } from "@/hooks/use-document-upload";

/**
 * Full-page fallback for direct linking (specs/ui-ux.md §6) — the primary
 * upload entry point is the modal (UploadDialog); this route reuses the
 * exact same dropzone/file-row pair, never a second implementation.
 */
export function UploadView() {
  const { items, addFiles, retry, remove } = useDocumentUpload();

  return (
    <>
      <PageHeader
        title="Upload a document"
        description="PDF, DOCX, TXT, or CSV — up to the plan's size limit."
      />
      <UploadDropzone onFilesSelected={addFiles} />
      {items.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2" aria-live="polite">
          {items.map((item) => (
            <UploadFileRow
              key={item.clientId}
              item={item}
              onRetry={() => retry(item.clientId)}
              onRemove={() => remove(item.clientId)}
            />
          ))}
        </ul>
      )}
    </>
  );
}
