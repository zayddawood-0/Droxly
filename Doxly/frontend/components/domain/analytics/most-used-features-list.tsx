import type { FeatureUsage } from "@/lib/api/analytics";

const FEATURE_LABELS: Record<string, string> = {
  chat: "AI Chat",
  summarization: "Summarization",
  extraction: "Extraction",
  comparison: "Comparison",
  search: "Search",
};

function humanizeFeature(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature.charAt(0).toUpperCase() + feature.slice(1);
}

/** ui-ux.md §13 — "a 'most-used features' small list/bar." Real list markup, not a chart. */
export function MostUsedFeaturesList({ features }: { features: FeatureUsage[] }) {
  const max = Math.max(...features.map((f) => f.count), 1);

  return (
    <ul className="flex flex-col gap-3">
      {features.map((feature) => (
        <li key={feature.feature} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-sm">{humanizeFeature(feature.feature)}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.round((feature.count / max) * 100)}%` }}
            />
          </div>
          <span className="w-8 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
            {feature.count}
          </span>
        </li>
      ))}
    </ul>
  );
}
