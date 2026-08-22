import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileTypeIcon } from "@/components/domain/documents/file-type-icon";
import { StatusBadge } from "@/components/domain/documents/status-badge";
import { DocumentRowActions } from "@/components/domain/documents/document-row-actions";
import { formatBytes } from "@/lib/constants/documents";
import { cn } from "@/lib/utils";
import type { DocumentListItem } from "@/lib/api/documents";

/**
 * Used both in Documents' grid view and Dashboard's "Recent documents"
 * compact cards (specs/ui-ux.md §4/§5) — one component, a `compact` prop
 * for the smaller Dashboard density, never two near-identical components.
 */
export function DocumentCard({
  document,
  compact = false,
}: {
  document: DocumentListItem;
  compact?: boolean;
}) {
  return (
    <Link
      href={`/documents/${document.id}`}
      className="block rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <Card
        className={cn(
          "relative gap-2 transition-colors hover:border-muted-foreground/40",
          compact ? "p-3" : "p-4",
        )}
      >
        {!compact && (
          <div className="absolute top-2 right-2">
            <DocumentRowActions document={document} />
          </div>
        )}
        <div className="flex items-start gap-2.5 pr-6">
          <FileTypeIcon mimeType={document.mime_type} className="mt-0.5 size-5" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{document.file_name}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {formatBytes(document.size_bytes)}
              {document.page_count ? ` · ${document.page_count} pages` : ""}
            </p>
          </div>
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <StatusBadge status={document.status} variant="compact" />
          {!compact &&
            document.tags.slice(0, 3).map((tag) => (
              <Badge key={tag.id} variant="outline" className="font-normal">
                {tag.name}
              </Badge>
            ))}
        </div>
      </Card>
    </Link>
  );
}
