import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** ui-ux.md §13 — "a grid of compact stat cards." */
export function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
  label: string;
  value: string;
}) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        <span className="text-xs">{label}</span>
      </div>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
    </Card>
  );
}

export function StatCardSkeleton() {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-7 w-16" />
    </Card>
  );
}
