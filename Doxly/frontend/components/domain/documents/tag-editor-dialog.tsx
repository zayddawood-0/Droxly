"use client";

import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { useTagsQuery, useCreateTagMutation } from "@/hooks/use-tags";
import { useUpdateDocumentMutation } from "@/hooks/use-documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import type { DocumentTagRef } from "@/lib/api/documents";

/** FR-DOC-006 — specs/ui-ux.md §5's tag editor Dialog. */
export function TagEditorDialog({
  documentId,
  currentTags,
  open,
  onOpenChange,
}: {
  documentId: string;
  currentTags: DocumentTagRef[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(currentTags.map((tag) => tag.id)),
  );
  const [newTagName, setNewTagName] = useState("");
  const [saving, setSaving] = useState(false);

  const tagsQuery = useTagsQuery();
  const createTag = useCreateTagMutation();
  const updateDocument = useUpdateDocumentMutation();

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleCreateTag() {
    const name = newTagName.trim();
    if (!name) return;
    try {
      const tag = await createTag.mutateAsync({ name });
      setSelectedIds((prev) => new Set(prev).add(tag.id));
      setNewTagName("");
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't create that tag. Please try again.",
      );
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateDocument.mutateAsync({
        id: documentId,
        tag_ids: Array.from(selectedIds),
      });
      toast.success("Tags updated");
      onOpenChange(false);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't update tags. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Tags</DialogTitle>
          <DialogDescription>Choose which tags apply to this document.</DialogDescription>
        </DialogHeader>

        {tagsQuery.isPending ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-2/3" />
          </div>
        ) : tagsQuery.isError ? (
          <p className="text-sm text-danger">Couldn&apos;t load your tags.</p>
        ) : tagsQuery.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tags yet — create your first one below.</p>
        ) : (
          <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto">
            {tagsQuery.data.items.map((tag) => (
              <li key={tag.id}>
                <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                  <Checkbox
                    checked={selectedIds.has(tag.id)}
                    onCheckedChange={() => toggle(tag.id)}
                  />
                  {tag.name}
                </label>
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center gap-2">
          <Input
            placeholder="New tag name"
            value={newTagName}
            onChange={(event) => setNewTagName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void handleCreateTag();
              }
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={handleCreateTag}
            disabled={!newTagName.trim() || createTag.isPending}
            aria-label="Create tag"
          >
            <Plus className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="animate-spin" aria-hidden="true" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
