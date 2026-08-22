"use client";

import { Check, PencilLine, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useEditableField } from "@/hooks/use-editable-field";
import { ConfidenceBadge } from "@/components/domain/extractions/confidence-badge";
import type { ExtractionResultField } from "@/lib/api/extractions";

/**
 * ui-ux.md §10 — one row of the results table: Field | Value | Confidence
 * | Source | Edit. A `not_found` field renders in a muted, explicitly
 * distinct state with the reason (FR-EXT-003) — never styled like a blank
 * value a user might mistake for their own data gap to fill in.
 */
export function ExtractionFieldRow({
  field,
  onSave,
}: {
  field: ExtractionResultField;
  onSave: (value: string) => Promise<void>;
}) {
  const editable = useEditableField(field.value, onSave);
  const notFound = field.value === null && field.not_found_reason;

  return (
    <TableRow>
      <TableCell className="font-medium">{field.field}</TableCell>
      <TableCell>
        {editable.editing ? (
          <div className="flex items-center gap-1">
            <Input
              autoFocus
              value={editable.draft}
              onChange={(event) => editable.setDraft(event.target.value)}
              onKeyDown={editable.handleKeyDown}
              aria-label={`Edit value for ${field.field}`}
              className="h-8"
            />
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={editable.confirm}
              disabled={editable.saving}
              aria-label="Save"
            >
              <Check className="size-4" aria-hidden="true" />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={editable.cancel} aria-label="Cancel">
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        ) : notFound ? (
          <span className="text-sm text-muted-foreground italic">Not found in document</span>
        ) : (
          <span className={cn("text-sm", field.corrected && "text-primary")}>
            {String(field.value)}
          </span>
        )}
      </TableCell>
      <TableCell>
        <ConfidenceBadge confidence={field.confidence} />
      </TableCell>
      <TableCell className="max-w-48 truncate text-xs text-muted-foreground">
        {field.citation
          ? `${field.citation.page_number ? `p. ${field.citation.page_number} — ` : ""}${field.citation.snippet}`
          : "—"}
      </TableCell>
      <TableCell>
        {!editable.editing && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={editable.startEdit}
            aria-label={`Edit ${field.field}`}
          >
            <PencilLine className="size-4" aria-hidden="true" />
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}
