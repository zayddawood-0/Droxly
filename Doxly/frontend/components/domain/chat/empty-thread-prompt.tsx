import { Sparkles } from "lucide-react";

const EXAMPLE_QUERIES = [
  "What are the key takeaways from this document?",
  "Summarize the main points in a few sentences.",
  "Are there any deadlines or dates mentioned?",
];

/**
 * ui-ux.md §8 — shared empty state for "no conversations yet" and "empty
 * active thread," both showing prompt suggestions instead of a blank pane.
 */
export function EmptyThreadPrompt({ onPick }: { onPick?: (query: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-accent">
        <Sparkles className="size-6 text-accent-foreground" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-medium">Ask a question about your documents</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Answers are grounded in your own documents, always cited.
        </p>
      </div>
      <div className="flex flex-col gap-2">
        {EXAMPLE_QUERIES.map((query) => (
          <button
            key={query}
            type="button"
            onClick={() => onPick?.(query)}
            className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {query}
          </button>
        ))}
      </div>
    </div>
  );
}
