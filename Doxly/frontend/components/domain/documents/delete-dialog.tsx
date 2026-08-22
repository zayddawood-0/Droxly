"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useDeleteDocumentMutation } from "@/hooks/use-documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

/**
 * FR-DOC-005 — a plain confirmation, deliberately NOT the typed-confirmation
 * pattern account deletion uses (design.md §3.3: document deletion is
 * reversible-enough and common enough that over-friction would erode trust
 * in the product's speed).
 */
export function DeleteDialog({
  documentId,
  fileName,
  open,
  onOpenChange,
  onDeleted,
}: {
  documentId: string;
  fileName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fires after a successful delete, before the dialog closes — e.g. to redirect away from a now-gone document's page. */
  onDeleted?: () => void;
}) {
  const [pending, setPending] = useState(false);
  const mutation = useDeleteDocumentMutation();

  async function handleDelete() {
    setPending(true);
    try {
      await mutation.mutateAsync(documentId);
      toast.success("Document deleted");
      onOpenChange(false);
      onDeleted?.();
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't delete this document. Please try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete “{fileName}”?</DialogTitle>
          <DialogDescription>
            This removes it from your documents immediately. This can&apos;t be undone from here.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" onClick={handleDelete} disabled={pending}>
            {pending && <Loader2 className="animate-spin" aria-hidden="true" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
