"use client";

import { useState } from "react";
import { MoreHorizontal, Download, FileOutput, PencilLine, Tags, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { RenameDialog } from "@/components/domain/documents/rename-dialog";
import { DeleteDialog } from "@/components/domain/documents/delete-dialog";
import { TagEditorDialog } from "@/components/domain/documents/tag-editor-dialog";
import { SummaryDialog } from "@/components/domain/summaries/summary-dialog";
import { getDownloadUrl } from "@/lib/api/documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import type { DocumentListItem } from "@/lib/api/documents";

export function DocumentRowActions({ document }: { document: DocumentListItem }) {
  const [dialog, setDialog] = useState<"rename" | "delete" | "tags" | "summaries" | null>(null);

  async function handleDownload() {
    try {
      const { download_url } = await getDownloadUrl(document.id);
      window.open(download_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't prepare a download link. Please try again.",
      );
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Actions for ${document.file_name}`}
              onClick={(event: React.MouseEvent) => event.preventDefault()}
            />
          }
        >
          <MoreHorizontal className="size-4" aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={handleDownload}>
            <Download className="size-4" aria-hidden="true" />
            Download
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setDialog("rename")}>
            <PencilLine className="size-4" aria-hidden="true" />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setDialog("tags")}>
            <Tags className="size-4" aria-hidden="true" />
            Tags
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setDialog("summaries")}>
            <FileOutput className="size-4" aria-hidden="true" />
            Summarize
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onClick={() => setDialog("delete")}>
            <Trash2 className="size-4" aria-hidden="true" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <RenameDialog
        documentId={document.id}
        currentName={document.file_name}
        open={dialog === "rename"}
        onOpenChange={(open) => setDialog(open ? "rename" : null)}
      />
      <DeleteDialog
        documentId={document.id}
        fileName={document.file_name}
        open={dialog === "delete"}
        onOpenChange={(open) => setDialog(open ? "delete" : null)}
      />
      <TagEditorDialog
        documentId={document.id}
        currentTags={document.tags}
        open={dialog === "tags"}
        onOpenChange={(open) => setDialog(open ? "tags" : null)}
      />
      <SummaryDialog
        documentId={document.id}
        open={dialog === "summaries"}
        onOpenChange={(open) => setDialog(open ? "summaries" : null)}
      />
    </>
  );
}
