import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** ui-ux.md §10 — "confidence is conveyed with text/icon in addition to color" (NFR-A11Y-001), never color alone. */
export function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence === null) {
    return (
      <Badge variant="outline" className="font-normal text-muted-foreground">
        —
      </Badge>
    );
  }

  const percent = Math.round(confidence * 100);
  const level = confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";

  return (
    <Badge
      className={cn(
        "font-normal tabular-nums",
        level === "high" && "bg-success-soft text-success",
        level === "medium" && "bg-info-soft text-info",
        level === "low" && "bg-danger-soft text-danger",
      )}
    >
      {percent}%
    </Badge>
  );
}
