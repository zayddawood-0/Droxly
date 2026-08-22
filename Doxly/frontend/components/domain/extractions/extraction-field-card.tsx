"use client";

import { Check, PencilLine, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useEditableField } from "@/hooks/use-editable-field";
import { ConfidenceBadge } from "@/components/domain/extractions/confidence-badge";
import type { ExtractionResultField } from "@/lib/api/extractions";

/** ui-ux.md §10 — "Field table becomes a stacked card-per-field layout on mobile (label/value/confidence/source stacked, not a horizontally scrolling table)." Same edit behavior as the desktop row. */
export function ExtractionFieldCard({
  field,
  onSave,
}: {
  field: ExtractionResultField;
  onSave: (value: string) => Promise<void>;
}) {
  const editable = useEditableField(field.value, onSave);
  const notFound = field.value === null && field.not_found_reason;

  return (
    <Card className="flex flex-col gap-2 p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{field.field}</span>
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
      </div>

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
          <Button variant="ghost" size="icon-sm" onClick={editable.confirm} disabled={editable.saving} aria-label="Save">
            <Check className="size-4" aria-hidden="true" />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={editable.cancel} aria-label="Cancel">
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : notFound ? (
        <span className="text-sm text-muted-foreground italic">Not found in document</span>
      ) : (
        <span className={cn("text-sm", field.corrected && "text-primary")}>{String(field.value)}</span>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <ConfidenceBadge confidence={field.confidence} />
        <span className="max-w-40 truncate">
          {field.citation
            ? `${field.citation.page_number ? `p. ${field.citation.page_number} — ` : ""}${field.citation.snippet}`
            : "—"}
        </span>
      </div>
    </Card>
  );
}
