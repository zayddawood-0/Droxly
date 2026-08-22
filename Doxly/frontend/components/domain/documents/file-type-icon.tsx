import { FileText, FileSpreadsheet, File as FileIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const ICON_BY_MIME: Record<string, typeof FileText> = {
  "application/pdf": FileText,
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileText,
  "text/csv": FileSpreadsheet,
  "text/plain": FileIcon,
};

export function FileTypeIcon({
  mimeType,
  className,
}: {
  mimeType: string;
  className?: string;
}) {
  const Icon = ICON_BY_MIME[mimeType] ?? FileIcon;
  return <Icon className={cn("size-4 shrink-0 text-muted-foreground", className)} aria-hidden="true" />;
}
