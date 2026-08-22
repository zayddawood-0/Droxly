"use client";

import { FileEdit, FileText } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useExtractionTemplatesQuery } from "@/hooks/use-extractions";

/** ui-ux.md §10 — "TemplateGallery (cards: Invoice, Contract, Resume, Research Paper, per FR-EXT-002)" plus the "Custom schema" escape hatch. */
export function TemplateGallery({
  selectedKey,
  onSelect,
  onSelectCustom,
}: {
  selectedKey: string | null;
  onSelect: (key: string) => void;
  onSelectCustom: () => void;
}) {
  const query = useExtractionTemplatesQuery();

  if (query.isPending) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-6 py-8 text-center">
        <p className="text-sm text-muted-foreground">Couldn&apos;t load extraction templates.</p>
        <Button variant="outline" size="sm" onClick={() => query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {query.data.items.map((template) => (
        <button key={template.key} type="button" onClick={() => onSelect(template.key)} className="text-left">
          <Card
            className={cn(
              "flex flex-col gap-1 p-4 transition-colors hover:border-muted-foreground/40",
              selectedKey === template.key && "border-primary ring-1 ring-primary",
            )}
          >
            <span className="flex items-center gap-2 font-medium">
              <FileText className="size-4 text-muted-foreground" aria-hidden="true" />
              {template.name}
            </span>
            <span className="text-xs text-muted-foreground">{template.description}</span>
            <span className="mt-1 text-xs text-muted-foreground">
              {template.fields.length} field{template.fields.length === 1 ? "" : "s"}
            </span>
          </Card>
        </button>
      ))}

      <button type="button" onClick={onSelectCustom} className="text-left">
        <Card className="flex h-full flex-col items-start justify-center gap-1 border-dashed p-4 transition-colors hover:border-muted-foreground/40">
          <span className="flex items-center gap-2 font-medium">
            <FileEdit className="size-4 text-muted-foreground" aria-hidden="true" />
            Custom schema
          </span>
          <span className="text-xs text-muted-foreground">Define your own fields to extract.</span>
        </Card>
      </button>
    </div>
  );
}
