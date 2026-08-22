import { AlertTriangle, Hash, Minus, PenLine, Plus, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ChangeType } from "@/lib/api/comparisons";

export type ChangeBadgeKind = "addition" | "deletion" | "modification" | ChangeType;

const CONFIG: Record<ChangeBadgeKind, { label: string; icon: typeof Plus; className: string }> = {
  addition: { label: "Added", icon: Plus, className: "bg-success-soft text-success" },
  deletion: { label: "Removed", icon: Minus, className: "bg-danger-soft text-danger" },
  modification: { label: "Changed", icon: RefreshCw, className: "bg-info-soft text-info" },
  factual: { label: "Factual", icon: AlertTriangle, className: "bg-warning-soft text-warning" },
  numeric: { label: "Numeric", icon: Hash, className: "bg-primary/10 text-primary" },
  wording: { label: "Wording", icon: PenLine, className: "border-border text-muted-foreground" },
};

/**
 * ui-ux.md §11 — "ChangeTypeBadge (addition/deletion/modification/factual/
 * numeric/wording, each a distinct color+icon pairing)" and "carry text
 * labels, not color alone" (accessibility). `wording` intentionally reuses
 * the outline treatment rather than a semantic color — the four semantic
 * tokens (success/warning/danger/info) are exhausted by the other five
 * kinds, so its icon+label pairing is what makes it distinct, per spec.
 */
export function ChangeTypeBadge({ kind }: { kind: ChangeBadgeKind }) {
  const { label, icon: Icon, className } = CONFIG[kind];
  return (
    <Badge variant={kind === "wording" ? "outline" : "default"} className={cn("font-normal", className)}>
      <Icon className="size-3" aria-hidden="true" />
      {label}
    </Badge>
  );
}
