"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { cn } from "@/lib/utils";
import { ACCEPTED_FILE_EXTENSIONS, ACCEPTED_TYPES_LABEL, formatBytes, MAX_FILE_SIZE_BYTES } from "@/lib/constants/documents";

/**
 * The one dropzone (specs/ui-ux.md §15 File Upload Conventions) reused
 * identically wherever upload appears. Four states: idle, drag-over
 * (accent border), uploading (handled by the caller's file-row list below
 * it, not this component), error (also caller-rendered). A real interactive
 * element reachable by keyboard — Enter/Space opens the file picker.
 */
export function UploadDropzone({ onFilesSelected }: { onFilesSelected: (files: File[]) => void }) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    onFilesSelected(Array.from(fileList));
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Drag files here or click to browse. Accepts ${ACCEPTED_TYPES_LABEL}, up to ${formatBytes(MAX_FILE_SIZE_BYTES)} each.`}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors cursor-pointer outline-none",
        "focus-visible:ring-3 focus-visible:ring-ring/50",
        dragActive ? "border-primary bg-accent/50" : "border-border hover:border-muted-foreground/50",
      )}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragActive(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      <UploadCloud className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm font-medium">Drag files here or click to browse</p>
      <p className="text-xs text-muted-foreground">
        {ACCEPTED_TYPES_LABEL} — up to {formatBytes(MAX_FILE_SIZE_BYTES)} each
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_FILE_EXTENSIONS.join(",")}
        className="sr-only"
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </div>
  );
}
