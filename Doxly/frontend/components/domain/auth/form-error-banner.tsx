"use client";

import { TriangleAlert, X } from "lucide-react";
import { Alert, AlertDescription, AlertAction } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * The dismissible network/server-error banner specs/ui-ux.md §2 calls for —
 * distinct from an inline credential error (which is field-scoped and clears
 * on the next submit, not something a user needs to dismiss). Used when the
 * request itself failed (no response, 5xx, or this app's own BFF proxy
 * returning 502 because the backend isn't reachable — specs/security.md
 * §11.2's sanitized-error principle: never a raw network exception shown).
 */
export function FormErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <Alert variant="destructive" className="mb-4">
      <TriangleAlert />
      <AlertDescription>{message}</AlertDescription>
      <AlertAction>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          <X />
        </Button>
      </AlertAction>
    </Alert>
  );
}
