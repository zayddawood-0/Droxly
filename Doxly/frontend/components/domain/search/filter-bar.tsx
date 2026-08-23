"use client";

import { SlidersHorizontal } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useTagsQuery } from "@/hooks/use-tags";
import { STAGE_LABEL } from "@/components/domain/documents/status-badge";
import type { DocumentStatus } from "@/lib/api/documents";

export type SearchFilters = {
  mimeType: string;
  tagId: string;
  status: DocumentStatus | "all";
  dateFrom: string;
  dateTo: string;
};

export const EMPTY_SEARCH_FILTERS: SearchFilters = {
  mimeType: "all",
  tagId: "all",
  status: "all",
  dateFrom: "",
  dateTo: "",
};

const MIME_TYPE_OPTIONS = [
  { value: "all", label: "All types" },
  { value: "application/pdf", label: "PDF" },
  { value: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", label: "Word" },
  { value: "text/csv", label: "CSV" },
  { value: "text/plain", label: "Text" },
];

const STATUS_OPTIONS: { value: DocumentStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  ...(Object.entries(STAGE_LABEL) as [DocumentStatus, string][]).map(([value, label]) => ({
    value,
    label,
  })),
];

export function countActiveFilters(filters: SearchFilters): number {
  return (
    (filters.mimeType !== "all" ? 1 : 0) +
    (filters.tagId !== "all" ? 1 : 0) +
    (filters.status !== "all" ? 1 : 0) +
    (filters.dateFrom !== "" ? 1 : 0) +
    (filters.dateTo !== "" ? 1 : 0)
  );
}

/** ui-ux.md §12 — "filter row (type/tag/date)"; collapses into a "Filters" sheet on mobile. */
export function FilterBar({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (patch: Partial<SearchFilters>) => void;
}) {
  const tagsQuery = useTagsQuery();
  const activeCount = countActiveFilters(filters);

  const controls = (
    <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="search-filter-type" className="text-xs text-muted-foreground">
          Type
        </Label>
        <Select value={filters.mimeType} onValueChange={(v) => onChange({ mimeType: v ?? "all" })}>
          <SelectTrigger id="search-filter-type" className="w-full sm:w-36" aria-label="Filter by document type">
            <SelectValue>
              {(value: string) => MIME_TYPE_OPTIONS.find((o) => o.value === value)?.label ?? "All types"}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {MIME_TYPE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="search-filter-tag" className="text-xs text-muted-foreground">
          Tag
        </Label>
        <Select value={filters.tagId} onValueChange={(v) => onChange({ tagId: v ?? "all" })}>
          <SelectTrigger id="search-filter-tag" className="w-full sm:w-36" aria-label="Filter by tag">
            <SelectValue>
              {(value: string) =>
                value === "all"
                  ? "All tags"
                  : (tagsQuery.data?.items.find((tag) => tag.id === value)?.name ?? "All tags")
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All tags</SelectItem>
            {tagsQuery.data?.items.map((tag) => (
              <SelectItem key={tag.id} value={tag.id}>
                {tag.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="search-filter-status" className="text-xs text-muted-foreground">
          Status
        </Label>
        <Select
          value={filters.status}
          onValueChange={(v) => onChange({ status: (v ?? "all") as SearchFilters["status"] })}
        >
          <SelectTrigger id="search-filter-status" className="w-full sm:w-36" aria-label="Filter by status">
            <SelectValue>
              {(value: SearchFilters["status"]) =>
                STATUS_OPTIONS.find((o) => o.value === value)?.label ?? "All statuses"
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="search-filter-from" className="text-xs text-muted-foreground">
          From
        </Label>
        <Input
          id="search-filter-from"
          type="date"
          value={filters.dateFrom}
          onChange={(e) => onChange({ dateFrom: e.target.value })}
          className="w-full sm:w-36"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="search-filter-to" className="text-xs text-muted-foreground">
          To
        </Label>
        <Input
          id="search-filter-to"
          type="date"
          value={filters.dateTo}
          onChange={(e) => onChange({ dateTo: e.target.value })}
          className="w-full sm:w-36"
        />
      </div>

      {activeCount > 0 && (
        <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_SEARCH_FILTERS)} className="self-end">
          Clear filters
        </Button>
      )}
    </>
  );

  return (
    <>
      <div className="hidden flex-wrap items-end gap-3 sm:flex">{controls}</div>

      <div className="sm:hidden">
        <Sheet>
          <SheetTrigger
            render={
              <Button variant="outline" size="sm" className="gap-1.5">
                <SlidersHorizontal className="size-4" aria-hidden="true" />
                Filters
                {activeCount > 0 && (
                  <Badge className="ml-0.5 h-4 min-w-4 px-1 tabular-nums">{activeCount}</Badge>
                )}
              </Button>
            }
          />
          <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
            </SheetHeader>
            <div className="flex flex-col gap-4 p-4 pt-0">{controls}</div>
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
