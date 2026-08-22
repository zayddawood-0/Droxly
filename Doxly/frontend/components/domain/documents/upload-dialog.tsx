"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { UploadDropzone } from "@/components/domain/documents/upload-dropzone";
import { UploadFileRow } from "@/components/domain/documents/upload-file-row";
import { useDocumentUpload } from "@/hooks/use-document-upload";

/**
 * The primary Upload entry point (specs/ui-ux.md §6: "spec assumes a modal
 * for a lighter feel, with a full-page fallback route for direct linking" —
 * see app/(dashboard)/documents/upload/page.tsx for that fallback, which
 * reuses this same dropzone/file-row pair, never a second implementation).
 */
export function UploadDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { items, addFiles, retry, remove, reset } = useDocumentUpload();
  const announcedDoneCount = useRef(0);

  useEffect(() => {
    if (open) return;
    const doneCount = items.filter((item) => item.status === "done").length;
    if (doneCount > 0 && doneCount !== announcedDoneCount.current) {
      toast.success(
        doneCount === 1
          ? "1 document uploaded"
          : `${doneCount} documents uploaded`,
      );
      announcedDoneCount.current = doneCount;
    }
    if (items.length > 0) {
      const timeout = setTimeout(reset, 300);
      return () => clearTimeout(timeout);
    }
  }, [open, items, reset]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
          <DialogDescription>
            PDF, DOCX, TXT, or CSV. You can select more than one.
          </DialogDescription>
        </DialogHeader>

        <UploadDropzone onFilesSelected={addFiles} />

        {items.length > 0 && (
          <ul className="flex max-h-64 flex-col gap-2 overflow-y-auto" aria-live="polite">
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
      </DialogContent>
    </Dialog>
  );
}
