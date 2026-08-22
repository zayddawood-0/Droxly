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
 * A single-document combobox — named `DocumentPicker` in ui-ux.md §11
 * (Comparison, "DocumentPicker (×2)") and implied by §10's "document
 * selection step" (Extraction). Built once here so Comparison reuses it
 * rather than a second implementation of the same picker.
 */
export function DocumentPicker({
  selectedId,
  onChange,
  placeholder = "Select a document…",
  disabled,
  excludeId,
}: {
  selectedId: string | null;
  onChange: (id: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Hides one document from the list — e.g. Comparison's Document B picker excludes whatever Document A already selected, mirroring the API's `422 identical_documents` guard client-side. */
  excludeId?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const query = useDocumentsQuery({ status: "ready", limit: 100 });
  const documents = (query.data?.items ?? []).filter((document) => document.id !== excludeId);
  const selected = documents.find((document) => document.id === selectedId);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={<Button variant="outline" disabled={disabled} className="w-full justify-between" />}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className={selected ? "truncate" : "truncate text-muted-foreground"}>
            {selected?.file_name ?? placeholder}
          </span>
        </span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-0">
        <Command>
          <CommandInput placeholder="Search documents…" />
          <CommandList>
            {query.isPending ? (
              <div className="p-3 text-sm text-muted-foreground">Loading documents…</div>
            ) : query.isError ? (
              <div className="p-3 text-sm text-muted-foreground">Couldn&apos;t load your documents.</div>
            ) : documents.length === 0 ? (
              <CommandEmpty>No ready documents yet.</CommandEmpty>
            ) : (
              <CommandGroup>
                {documents.map((document) => (
                  <CommandItem
                    key={document.id}
                    data-checked={document.id === selectedId}
                    onSelect={() => {
                      onChange(document.id);
                      setOpen(false);
                    }}
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
