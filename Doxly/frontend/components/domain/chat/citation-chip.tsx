import Link from "next/link";
import { FileText } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { MessageCitation } from "@/lib/api/chat";

/**
 * ui-ux.md §8 — "citation chips are clickable and deep-link to the
 * Document Viewer at the cited page/snippet"; "descriptive accessible
 * names ('Citation: page 4')" (NFR-A11Y-001).
 */
export function CitationChip({ citation, index }: { citation: MessageCitation; index: number }) {
  const label = citation.page_number
    ? `Citation ${index + 1}: page ${citation.page_number}`
    : `Citation ${index + 1}`;

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Link
            href={`/documents/${citation.document_id}${citation.page_number ? `?page=${citation.page_number}` : ""}`}
            aria-label={label}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          />
        }
      >
        <FileText className="size-3" aria-hidden="true" />
        {citation.page_number ? `p. ${citation.page_number}` : `Source ${index + 1}`}
      </TooltipTrigger>
      <TooltipContent>{citation.snippet}</TooltipContent>
    </Tooltip>
  );
}
