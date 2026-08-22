import { FileUp, FilterX } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Two distinct empty states (specs/ui-ux.md §4/§5) that must look
 * different so a user never mistakes "no results for this filter" for
 * "I lost all my documents." Shared between Documents and Dashboard, which
 * use identical guidance for the zero-documents case.
 */
export function DocumentsEmptyState({
  variant,
  onUpload,
  onClearFilters,
}: {
  variant: "no-documents" | "no-results";
  onUpload?: () => void;
  onClearFilters?: () => void;
}) {
  if (variant === "no-results") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
        <FilterX className="size-8 text-muted-foreground" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium">No documents match these filters</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Try different filters or clear them to see everything.
          </p>
        </div>
        {onClearFilters && (
          <Button variant="outline" size="sm" onClick={onClearFilters}>
            Clear filters
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
      <FileUp className="size-8 text-muted-foreground" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium">Upload your first document</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          Upload a PDF, DOCX, TXT, or CSV to start asking questions, extracting data, and comparing documents.
        </p>
      </div>
      {onUpload && (
        <Button size="sm" onClick={onUpload}>
          Upload your first document
        </Button>
      )}
    </div>
  );
}
