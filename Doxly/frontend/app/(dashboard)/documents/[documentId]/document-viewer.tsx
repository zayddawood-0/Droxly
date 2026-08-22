"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Sparkles,
  FileSearch,
  ArrowLeftRight,
  FileOutput,
  Download,
  PencilLine,
  Trash2,
  Tags,
} from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/domain/documents/status-badge";
import { FileTypeIcon } from "@/components/domain/documents/file-type-icon";
import { RenameDialog } from "@/components/domain/documents/rename-dialog";
import { DeleteDialog } from "@/components/domain/documents/delete-dialog";
import { TagEditorDialog } from "@/components/domain/documents/tag-editor-dialog";
import { useDocumentQuery, useReprocessDocumentMutation } from "@/hooks/use-documents";
import { useDocumentStatusStream } from "@/hooks/use-document-status-stream";
import { getDownloadUrl, type DocumentStatus } from "@/lib/api/documents";
import { formatBytes } from "@/lib/constants/documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import { isDoxlyApiError } from "@/lib/types/errors";

type DialogKind = "rename" | "delete" | "tags" | null;

export function DocumentViewer({ documentId }: { documentId: string }) {
  const router = useRouter();
  const query = useDocumentQuery(documentId);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const reprocess = useReprocessDocumentMutation();

  useDocumentStatusStream(documentId, query.data?.status);

  function handleReprocess() {
    reprocess.mutate(documentId, {
      onError: (error) => {
        toast.error(
          isConnectivityError(error)
            ? CONNECTIVITY_ERROR_MESSAGE
            : "Couldn't restart processing. Please try again.",
        );
      },
    });
  }

  async function handleDownload() {
    try {
      const { download_url } = await getDownloadUrl(documentId);
      window.open(download_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't prepare a download link. Please try again.",
      );
    }
  }

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = isDoxlyApiError(query.error) && query.error.status === 404;
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          {notFound
            ? "This document doesn't exist, or you don't have access to it."
            : "We couldn't load this document right now."}
        </p>
        <div className="flex gap-2">
          {!notFound && (
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Try again
            </Button>
          )}
          <Button variant="outline" size="sm" render={<Link href="/documents" />} nativeButton={false}>
            Back to Documents
          </Button>
        </div>
      </div>
    );
  }

  const document = query.data;

  return (
    <>
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <FileTypeIcon mimeType={document.mime_type} className="size-6" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold">{document.file_name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={document.status} processingError={document.processing_error} />
              <span className="text-xs text-muted-foreground">
                {formatBytes(document.size_bytes)}
                {document.page_count ? ` · ${document.page_count} pages` : ""}
              </span>
              {document.tags.map((tag) => (
                <Badge key={tag.id} variant="outline" className="font-normal">
                  {tag.name}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-6 lg:flex-row">
        <div className="min-w-0 flex-1 rounded-lg border border-border">
          <DocumentContentPane
            status={document.status}
            processingError={document.processing_error}
            onReprocess={handleReprocess}
            reprocessing={reprocess.isPending}
          />
        </div>

        <div className="flex gap-2 overflow-x-auto lg:w-56 lg:shrink-0 lg:flex-col lg:overflow-visible">
          <ActionButton icon={Sparkles} label="Chat about this" href={`/chat`} />
          <ActionButton icon={FileSearch} label="Extract" href={`/extractions`} />
          <ActionButton icon={ArrowLeftRight} label="Compare" href={`/compare`} />
          <ActionButton icon={FileOutput} label="Summarize" comingSoon />
          <div className="hidden border-t border-border lg:my-1 lg:block" />
          <ActionButton icon={Download} label="Download" onClick={handleDownload} />
          <ActionButton icon={PencilLine} label="Rename" onClick={() => setDialog("rename")} />
          <ActionButton icon={Tags} label="Tags" onClick={() => setDialog("tags")} />
          <ActionButton
            icon={Trash2}
            label="Delete"
            destructive
            onClick={() => setDialog("delete")}
          />
        </div>
      </div>

      <RenameDialog
        documentId={document.id}
        currentName={document.file_name}
        open={dialog === "rename"}
        onOpenChange={(open) => setDialog(open ? "rename" : null)}
      />
      <TagEditorDialog
        documentId={document.id}
        currentTags={document.tags}
        open={dialog === "tags"}
        onOpenChange={(open) => setDialog(open ? "tags" : null)}
      />
      <DeleteDialog
        documentId={document.id}
        fileName={document.file_name}
        open={dialog === "delete"}
        onOpenChange={(open) => setDialog(open ? "delete" : null)}
        onDeleted={() => router.push("/documents")}
      />
    </>
  );
}

const STAGE_DESCRIPTION: Record<string, string> = {
  queued: "Waiting in the processing queue — this is usually quick.",
  extracting: "Reading the file and pulling out its text.",
  chunking: "Splitting the extracted text into searchable sections.",
  embedding: "Generating semantic embeddings for search and chat.",
};

function DocumentContentPane({
  status,
  processingError,
  onReprocess,
  reprocessing,
}: {
  status: DocumentStatus;
  processingError: string | null;
  onReprocess: () => void;
  reprocessing: boolean;
}) {
  if (status === "ready") {
    // Extracted-text/original-file rendering is Phase 6+ scope (RAG/Q&A
    // land the retrieval pipeline this pane will eventually surface).
    return (
      <div className="flex flex-col items-center justify-center gap-2 px-6 py-24 text-center text-sm text-muted-foreground">
        Document content view is coming soon.
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-24 text-center">
        <StatusBadge status="failed" processingError={processingError} />
        <p className="text-sm font-medium text-danger">Processing failed</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          {processingError ?? "Something went wrong while processing this document."}
        </p>
        <Button variant="outline" size="sm" onClick={onReprocess} disabled={reprocessing}>
          {reprocessing ? "Retrying…" : "Retry processing"}
        </Button>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col items-center justify-center gap-3 px-6 py-24 text-center"
      aria-live="polite"
    >
      <StatusBadge status={status} />
      <p className="max-w-sm text-sm text-muted-foreground">{STAGE_DESCRIPTION[status]}</p>
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  href,
  onClick,
  destructive,
  comingSoon,
}: {
  icon: typeof Sparkles;
  label: string;
  href?: string;
  onClick?: () => void;
  destructive?: boolean;
  comingSoon?: boolean;
}) {
  const button = (
    <Button
      type="button"
      variant="ghost"
      disabled={comingSoon}
      className={cn(
        "w-full shrink-0 justify-start lg:w-full",
        destructive && "text-danger hover:text-danger",
      )}
      nativeButton={!href}
      render={href ? <Link href={href} /> : undefined}
      onClick={onClick}
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
    </Button>
  );

  if (!comingSoon) return button;

  return (
    <Tooltip>
      <TooltipTrigger render={<span className="inline-flex lg:w-full" />}>{button}</TooltipTrigger>
      <TooltipContent>Coming soon</TooltipContent>
    </Tooltip>
  );
}
