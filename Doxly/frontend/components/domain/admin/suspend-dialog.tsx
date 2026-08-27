"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSuspendUserMutation } from "@/hooks/use-admin";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

/**
 * ui-ux.md §15 — "suspend action requires confirmation" with "a required
 * reason field logged to audit_logs" (api.md §12's POST .../suspend body).
 */
export function SuspendDialog({
  userId,
  email,
  open,
  onOpenChange,
}: {
  userId: string;
  email: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [reason, setReason] = useState("");
  const mutation = useSuspendUserMutation();

  async function handleSuspend() {
    try {
      await mutation.mutateAsync({ id: userId, reason: reason.trim() });
      toast.success(`${email} suspended`);
      setReason("");
      onOpenChange(false);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't suspend this account. Please try again.",
      );
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setReason("");
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Suspend {email}?</DialogTitle>
          <DialogDescription>
            Immediately revokes every active session and blocks login, without deleting
            their data. A reason is required and recorded in the audit log.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Reason for suspension…"
          rows={3}
          aria-label="Suspension reason"
        />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleSuspend}
            disabled={mutation.isPending || reason.trim().length === 0}
          >
            {mutation.isPending && <Loader2 className="animate-spin" aria-hidden="true" />}
            Suspend
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
