import Link from "next/link";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { FileTypeIcon } from "@/components/domain/documents/file-type-icon";
import { StatusBadge } from "@/components/domain/documents/status-badge";
import { DocumentRowActions } from "@/components/domain/documents/document-row-actions";
import { formatBytes } from "@/lib/constants/documents";
import type { DocumentListItem } from "@/lib/api/documents";

/**
 * Desktop/tablet list view (specs/ui-ux.md §5). Collapses to DocumentCard's
 * grid below tablet width — a data table is not usable on a phone.
 */
export function DocumentTable({ documents }: { documents: DocumentListItem[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Tags</TableHead>
          <TableHead>Size</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Updated</TableHead>
          <TableHead className="w-10">
            <span className="sr-only">Actions</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((document) => (
          <TableRow key={document.id} className="group">
            <TableCell className="max-w-xs">
              <Link
                href={`/documents/${document.id}`}
                className="flex items-center gap-2.5 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 rounded-sm"
              >
                <FileTypeIcon mimeType={document.mime_type} />
                <span className="truncate font-medium group-hover:underline">
                  {document.file_name}
                </span>
              </Link>
            </TableCell>
            <TableCell>
              <div className="flex flex-wrap gap-1">
                {document.tags.slice(0, 2).map((tag) => (
                  <Badge key={tag.id} variant="outline" className="font-normal">
                    {tag.name}
                  </Badge>
                ))}
                {document.tags.length > 2 && (
                  <Badge variant="outline" className="font-normal text-muted-foreground">
                    +{document.tags.length - 2}
                  </Badge>
                )}
              </div>
            </TableCell>
            <TableCell className="tabular-nums text-muted-foreground">
              {formatBytes(document.size_bytes)}
            </TableCell>
            <TableCell>
              <StatusBadge status={document.status} variant="compact" />
            </TableCell>
            <TableCell className="tabular-nums text-muted-foreground">
              {new Date(document.updated_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </TableCell>
            <TableCell>
              <DocumentRowActions document={document} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
