import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AnalyticsPeriod } from "@/lib/api/analytics";

const OPTIONS: { value: AnalyticsPeriod; label: string }[] = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "90d", label: "90 days" },
];

/** ui-ux.md §13 — "period selector (7d/30d/90d) re-fetches chart data." */
export function PeriodSelector({
  value,
  onChange,
}: {
  value: AnalyticsPeriod;
  onChange: (period: AnalyticsPeriod) => void;
}) {
  return (
    <div role="group" aria-label="Time period" className="flex items-center gap-1 rounded-md border border-border p-0.5">
      {OPTIONS.map((option) => (
        <Button
          key={option.value}
          type="button"
          variant="ghost"
          size="sm"
          aria-pressed={value === option.value}
          className={cn(value === option.value && "bg-accent text-accent-foreground")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}
