"use client";

import { useState } from "react";
import { ChevronDown, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useDocumentsQuery } from "@/hooks/use-documents";

/**
 * ui-ux.md §8 — "DocumentScopePicker (multi-select combobox)"; empty
 * selection means workspace-wide (FR-AI-002), one selection is
 * single-document scope, more than one is multi-document scope.
 */
export function DocumentScopePicker({
  selectedIds,
  onChange,
  disabled,
}: {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const query = useDocumentsQuery({ status: "ready", limit: 100 });
  const documents = query.data?.items ?? [];

  const label =
    selectedIds.length === 0
      ? "All documents"
      : selectedIds.length === 1
        ? (documents.find((d) => d.id === selectedIds[0])?.file_name ?? "1 document")
        : `${selectedIds.length} documents`;

  function toggle(id: string) {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((existing) => existing !== id)
        : [...selectedIds, id],
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            disabled={disabled}
            className="max-w-64 justify-between"
          />
        }
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <FileText className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">{label}</span>
        </span>
        <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <Command>
          <CommandInput placeholder="Search documents…" />
          <CommandList>
            {query.isPending ? (
              <div className="p-3 text-sm text-muted-foreground">Loading documents…</div>
            ) : documents.length === 0 ? (
              <CommandEmpty>No ready documents yet.</CommandEmpty>
            ) : (
              <CommandGroup>
                <CommandItem onSelect={() => onChange([])} data-checked={selectedIds.length === 0}>
                  All documents (workspace-wide)
                </CommandItem>
                {documents.map((document) => (
                  <CommandItem
                    key={document.id}
                    onSelect={() => toggle(document.id)}
                    data-checked={selectedIds.includes(document.id)}
                  >
                    <span className="truncate">{document.file_name}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
