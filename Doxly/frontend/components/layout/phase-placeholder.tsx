import { Construction } from "lucide-react";

/**
 * Marks a route as structurally scaffolded but not yet feature-implemented.
 * Used only during Phase 1 (Foundation) — every page using this is replaced
 * with real content in the roadmap phase named below. Never shipped to a
 * user-facing build past its owning phase.
 */
export function PhasePlaceholder({
  phase,
  requirements,
}: {
  phase: string;
  requirements?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card/50 px-6 py-16 text-center">
      <Construction
        className="size-6 text-muted-foreground"
        aria-hidden="true"
      />
      <p className="text-sm text-muted-foreground">
        Not implemented yet — lands in{" "}
        <span className="font-medium text-foreground">{phase}</span>.
      </p>
      {requirements ? (
        <p className="font-mono text-xs text-muted-foreground/80">
          {requirements}
        </p>
      ) : null}
    </div>
  );
}
