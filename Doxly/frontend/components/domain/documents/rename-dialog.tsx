"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel, FieldError } from "@/components/ui/field";
import { useUpdateDocumentMutation } from "@/hooks/use-documents";
import {
  renameDocumentSchema,
  type RenameDocumentValues,
} from "@/lib/validation/documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

/** FR-DOC-004 — specs/ui-ux.md §5: renaming is a Dialog, never a page. */
export function RenameDialog({
  documentId,
  currentName,
  open,
  onOpenChange,
}: {
  documentId: string;
  currentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdateDocumentMutation();
  const form = useForm<RenameDocumentValues>({
    resolver: zodResolver(renameDocumentSchema),
    values: { file_name: currentName },
  });

  async function onSubmit(values: RenameDocumentValues) {
    try {
      await mutation.mutateAsync({ id: documentId, file_name: values.file_name });
      toast.success("Document renamed");
      onOpenChange(false);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't rename this document. Please try again.",
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Rename document</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
          <Field data-invalid={!!form.formState.errors.file_name}>
            <FieldLabel htmlFor="rename-file-name">Name</FieldLabel>
            <Input
              id="rename-file-name"
              autoFocus
              aria-invalid={!!form.formState.errors.file_name}
              {...form.register("file_name")}
            />
            <FieldError errors={[form.formState.errors.file_name]} />
          </Field>
          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting && (
                <Loader2 className="animate-spin" aria-hidden="true" />
              )}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
