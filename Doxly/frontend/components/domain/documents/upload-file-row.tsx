"use client";

import { CircleAlert, RotateCcw, X } from "lucide-react";
import { FileTypeIcon } from "@/components/domain/documents/file-type-icon";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/constants/documents";
import type { UploadItem } from "@/hooks/use-document-upload";

const STATUS_LABEL: Record<UploadItem["status"], string> = {
  uploading: "Uploading…",
  confirming: "Confirming…",
  done: "Queued for processing",
  error: "Failed",
};

export function UploadFileRow({
  item,
  onRetry,
  onRemove,
}: {
  item: UploadItem;
  onRetry: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-md border border-border px-3 py-2.5">
      <FileTypeIcon mimeType={item.file.type} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm font-medium">{item.file.name}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {formatBytes(item.file.size)}
          </span>
        </div>

        {item.status === "error" ? (
          <p className="mt-1 flex items-center gap-1.5 text-xs text-danger" role="alert">
            <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
            {item.error}
          </p>
        ) : (
          <div className="mt-1.5 flex items-center gap-2">
            <Progress value={item.status === "done" ? 100 : item.progress} className="h-1.5" />
            <span className="w-24 shrink-0 text-xs text-muted-foreground">
              {STATUS_LABEL[item.status]}
            </span>
          </div>
        )}
      </div>

      {item.status === "error" ? (
        <Button variant="ghost" size="icon-sm" onClick={onRetry} aria-label={`Retry uploading ${item.file.name}`}>
          <RotateCcw className="size-4" aria-hidden="true" />
        </Button>
      ) : null}
      <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label={`Remove ${item.file.name} from the upload list`}>
        <X className="size-4" aria-hidden="true" />
      </Button>
    </li>
  );
}
