"use client";

import { LayoutGrid, List, Search, Upload } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useTagsQuery } from "@/hooks/use-tags";
import type { DocumentListParams, DocumentStatus } from "@/lib/api/documents";

export type DocumentsFilters = {
  search: string;
  status: DocumentStatus | "all";
  tagId: string | "all";
  sort: NonNullable<DocumentListParams["sort"]>;
  view: "list" | "grid";
};

const STATUS_OPTIONS: { value: DocumentStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "queued", label: "Queued" },
  { value: "extracting", label: "Extracting" },
  { value: "chunking", label: "Chunking" },
  { value: "embedding", label: "Embedding" },
  { value: "ready", label: "Ready" },
  { value: "failed", label: "Failed" },
];

const SORT_OPTIONS: { value: DocumentsFilters["sort"]; label: string }[] = [
  { value: "created_at_desc", label: "Newest first" },
  { value: "created_at_asc", label: "Oldest first" },
  { value: "name_asc", label: "Name (A–Z)" },
  { value: "size_desc", label: "Largest first" },
];

/** specs/ui-ux.md §5 — search-within, filter controls, sort, view toggle, Upload. */
export function DocumentsToolbar({
  filters,
  onChange,
  onUpload,
}: {
  filters: DocumentsFilters;
  onChange: (patch: Partial<DocumentsFilters>) => void;
  onUpload: () => void;
}) {
  const tagsQuery = useTagsQuery();

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
      <div className="relative flex-1 sm:max-w-64">
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          value={filters.search}
          onChange={(event) => onChange({ search: event.target.value })}
          placeholder="Search this list…"
          className="pl-8"
          aria-label="Search documents in this list"
        />
      </div>

      <Select
        value={filters.status}
        onValueChange={(value) =>
          onChange({ status: (value ?? "all") as DocumentsFilters["status"] })
        }
      >
        <SelectTrigger className="w-40" aria-label="Filter by status">
          <SelectValue>
            {(value: DocumentsFilters["status"]) =>
              STATUS_OPTIONS.find((option) => option.value === value)?.label ?? "All statuses"
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

      <Select
        value={filters.tagId}
        onValueChange={(value) => onChange({ tagId: value ?? "all" })}
      >
        <SelectTrigger className="w-36" aria-label="Filter by tag">
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

      <Select
        value={filters.sort}
        onValueChange={(value) =>
          onChange({ sort: (value ?? "created_at_desc") as DocumentsFilters["sort"] })
        }
      >
        <SelectTrigger className="w-40" aria-label="Sort documents">
          <SelectValue>
            {(value: DocumentsFilters["sort"]) =>
              SORT_OPTIONS.find((option) => option.value === value)?.label ?? "Newest first"
            }
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {SORT_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="List view"
          aria-pressed={filters.view === "list"}
          className={cn(filters.view === "list" && "bg-accent text-accent-foreground")}
          onClick={() => onChange({ view: "list" })}
        >
          <List className="size-4" aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Grid view"
          aria-pressed={filters.view === "grid"}
          className={cn(filters.view === "grid" && "bg-accent text-accent-foreground")}
          onClick={() => onChange({ view: "grid" })}
        >
          <LayoutGrid className="size-4" aria-hidden="true" />
        </Button>
      </div>

      <Button type="button" onClick={onUpload} className="sm:ml-auto">
        <Upload className="size-4" aria-hidden="true" />
        Upload
      </Button>
    </div>
  );
}
