import { Loader2, Search } from "lucide-react";

import { Input } from "@/components/ui/input";

/**
 * ui-ux.md §12 — "prominent search input"; "lightweight inline spinner in
 * the search input area during debounce-triggered fetch, not a full-page
 * loader."
 */
export function SearchInput({
  value,
  onChange,
  loading,
  autoFocus,
}: {
  value: string;
  onChange: (value: string) => void;
  loading: boolean;
  autoFocus?: boolean;
}) {
  return (
    <div className="relative">
      <Search
        className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search across all your documents…"
        aria-label="Search documents"
        autoFocus={autoFocus}
        className="h-12 pl-11 pr-11 text-base"
      />
      {loading && (
        <Loader2
          className="absolute top-1/2 right-3.5 size-4 -translate-y-1/2 animate-spin text-muted-foreground"
          aria-hidden="true"
        />
      )}
    </div>
  );
}
