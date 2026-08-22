"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CitationChip } from "@/components/domain/chat/citation-chip";
import { ChangeTypeBadge, type ChangeBadgeKind } from "@/components/domain/comparisons/change-type-badge";
import { cn } from "@/lib/utils";
import type { ComparisonResult } from "@/lib/api/comparisons";
import type { SummaryFilter } from "@/components/domain/comparisons/change-summary-strip";

type NormalizedChange =
  | { id: string; kind: "addition"; badge: ChangeBadgeKind; page: number | null; excerpt: string }
  | { id: string; kind: "deletion"; badge: ChangeBadgeKind; page: number | null; excerpt: string }
  | {
      id: string;
      kind: "modification";
      badge: ChangeBadgeKind;
      aPage: number | null;
      aExcerpt: string;
      bPage: number | null;
      bExcerpt: string;
      explanation: string;
    };

function normalize(result: ComparisonResult): NormalizedChange[] {
  const changes: NormalizedChange[] = [
    ...result.additions.map((s, i) => ({
      id: `add-${i}`,
      kind: "addition" as const,
      badge: "addition" as ChangeBadgeKind,
      page: s.page_number,
      excerpt: s.excerpt,
    })),
    ...result.deletions.map((s, i) => ({
      id: `del-${i}`,
      kind: "deletion" as const,
      badge: "deletion" as ChangeBadgeKind,
      page: s.page_number,
      excerpt: s.excerpt,
    })),
    ...result.modifications.map((m, i) => ({
      id: `mod-${i}`,
      kind: "modification" as const,
      badge: m.change_type as ChangeBadgeKind,
      aPage: m.a_page_number,
      aExcerpt: m.a_excerpt,
      bPage: m.b_page_number,
      bExcerpt: m.b_excerpt,
      explanation: m.explanation,
    })),
  ];

  return changes.sort((x, y) => {
    const xPage = x.kind === "modification" ? (x.aPage ?? x.bPage) : x.page;
    const yPage = y.kind === "modification" ? (y.aPage ?? y.bPage) : y.page;
    return (xPage ?? Infinity) - (yPage ?? Infinity);
  });
}

function EmptySide() {
  return (
    <div className="rounded-md border border-dashed border-border/60 px-3 py-4 text-center text-xs text-muted-foreground">
      No corresponding content
    </div>
  );
}

function Excerpt({
  documentId,
  page,
  excerpt,
}: {
  documentId: string;
  page: number | null;
  excerpt: string;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border/60 px-3 py-2">
      <blockquote className="text-sm text-foreground">&ldquo;{excerpt}&rdquo;</blockquote>
      <CitationChip
        citation={{ document_id: documentId, page_number: page, snippet: excerpt, relevance_score: null }}
        index={0}
      />
    </div>
  );
}

/**
 * ui-ux.md §11 — "DiffView (side-by-side and unified variants)"; "clicking
 * a change scrolls/highlights the corresponding location in both documents
 * (side-by-side view)"; "diff regions are navigable via a 'next change'
 * keyboard shortcut for long documents." The desktop grid is genuinely
 * two-sided (Document A | Document B columns); mobile stacks the same
 * normalized change list into single cards, per the responsive spec.
 */
export function DiffView({
  result,
  documentAId,
  documentBId,
  filter,
}: {
  result: ComparisonResult;
  documentAId: string;
  documentBId: string;
  filter: SummaryFilter;
}) {
  const all = useMemo(() => normalize(result), [result]);
  const changes = filter ? all.filter((c) => c.kind === filter) : all;
  const [focusedIndex, setFocusedIndex] = useState(0);
  const refs = useRef<Record<string, HTMLDivElement | null>>({});

  function goTo(index: number) {
    const clamped = Math.max(0, Math.min(changes.length - 1, index));
    setFocusedIndex(clamped);
    const el = refs.current[changes[clamped]?.id ?? ""];
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.focus();
  }

  if (all.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
        No differences found between these documents.
      </p>
    );
  }

  if (changes.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
        No changes match this filter.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Change {focusedIndex + 1} of {changes.length}
        </p>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Previous change"
            onClick={() => goTo(focusedIndex - 1)}
            disabled={focusedIndex === 0}
          >
            <ChevronUp className="size-4" aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Next change"
            onClick={() => goTo(focusedIndex + 1)}
            disabled={focusedIndex === changes.length - 1}
          >
            <ChevronDown className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* Desktop: genuine side-by-side, Document A / Document B columns */}
      <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
        <div className="grid grid-cols-2 divide-x divide-border/60 border-b border-border/60 text-xs font-medium text-muted-foreground">
          <div className="px-3 py-2">Document A</div>
          <div className="px-3 py-2">Document B</div>
        </div>
        <div className="grid grid-cols-2 gap-x-0">
          {changes.map((change, i) => (
            <ChangeRow
              key={change.id}
              change={change}
              documentAId={documentAId}
              documentBId={documentBId}
              index={i}
              focused={i === focusedIndex}
              registerRef={(el) => {
                refs.current[change.id] = el;
              }}
            />
          ))}
        </div>
      </div>

      {/* Mobile / narrow tablet: unified stacked diff */}
      <div className="flex flex-col gap-3 md:hidden">
        {changes.map((change, i) => (
          <UnifiedCard
            key={change.id}
            change={change}
            documentAId={documentAId}
            documentBId={documentBId}
            focused={i === focusedIndex}
            registerRef={(el) => {
              refs.current[change.id] = el;
            }}
          />
        ))}
      </div>
    </div>
  );
}

function ChangeRow({
  change,
  documentAId,
  documentBId,
  index,
  focused,
  registerRef,
}: {
  change: NormalizedChange;
  documentAId: string;
  documentBId: string;
  index: number;
  focused: boolean;
  registerRef: (el: HTMLDivElement | null) => void;
}) {
  return (
    <div
      ref={registerRef}
      tabIndex={-1}
      data-testid={`change-row-${index}`}
      className={cn(
        "col-span-2 grid grid-cols-subgrid gap-x-0 border-b border-border/40 px-3 py-3 outline-none last:border-b-0",
        focused && "bg-accent/40",
      )}
    >
      <div className="col-span-2 mb-2 flex items-center gap-2">
        <ChangeTypeBadge kind={change.badge} />
        {change.kind === "modification" && (
          <p className="text-xs text-muted-foreground">{change.explanation}</p>
        )}
      </div>
      <div className="pr-3">
        {change.kind === "addition" ? (
          <EmptySide />
        ) : change.kind === "deletion" ? (
          <Excerpt documentId={documentAId} page={change.page} excerpt={change.excerpt} />
        ) : (
          <Excerpt documentId={documentAId} page={change.aPage} excerpt={change.aExcerpt} />
        )}
      </div>
      <div className="pl-3">
        {change.kind === "deletion" ? (
          <EmptySide />
        ) : change.kind === "addition" ? (
          <Excerpt documentId={documentBId} page={change.page} excerpt={change.excerpt} />
        ) : (
          <Excerpt documentId={documentBId} page={change.bPage} excerpt={change.bExcerpt} />
        )}
      </div>
    </div>
  );
}

function UnifiedCard({
  change,
  documentAId,
  documentBId,
  focused,
  registerRef,
}: {
  change: NormalizedChange;
  documentAId: string;
  documentBId: string;
  focused: boolean;
  registerRef: (el: HTMLDivElement | null) => void;
}) {
  return (
    <div
      ref={registerRef}
      tabIndex={-1}
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-border p-3 outline-none",
        focused && "bg-accent/40",
      )}
    >
      <div className="flex items-center gap-2">
        <ChangeTypeBadge kind={change.badge} />
      </div>
      {change.kind === "modification" && (
        <p className="text-xs text-muted-foreground">{change.explanation}</p>
      )}
      {change.kind !== "deletion" && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Document B</p>
          <Excerpt
            documentId={documentBId}
            page={change.kind === "modification" ? change.bPage : change.page}
            excerpt={change.kind === "modification" ? change.bExcerpt : change.excerpt}
          />
        </div>
      )}
      {change.kind !== "addition" && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Document A</p>
          <Excerpt
            documentId={documentAId}
            page={change.kind === "modification" ? change.aPage : change.page}
            excerpt={change.kind === "modification" ? change.aExcerpt : change.excerpt}
          />
        </div>
      )}
    </div>
  );
}
