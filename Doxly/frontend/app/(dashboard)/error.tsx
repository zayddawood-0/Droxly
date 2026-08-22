"use client";

import { useEffect } from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Route-segment error boundary for the authenticated app shell
 * (skills/frontend.md §1: "every route segment with meaningful failure modes
 * should define error.tsx"). Renders Doxly's calm/specific/actionable error
 * voice (design.md §4.3) — never a raw stack trace or generic "Something
 * went wrong" with no next step.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Client-side error boundary — server-side capture/reporting is wired
    // alongside real error tracking in a later phase (specs/observability.md §6).
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border px-6 py-16 text-center">
      <TriangleAlert className="size-8 text-danger" aria-hidden="true" />
      <div>
        <h2 className="text-base font-semibold">Something went wrong here</h2>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          This section couldn&apos;t load. The rest of Doxly is still working.
        </p>
      </div>
      <Button variant="outline" onClick={() => reset()}>
        Try again
      </Button>
    </div>
  );
}
