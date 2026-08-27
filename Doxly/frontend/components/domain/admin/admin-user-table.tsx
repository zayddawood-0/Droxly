"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SuspendDialog } from "@/components/domain/admin/suspend-dialog";
import { useUnsuspendUserMutation } from "@/hooks/use-admin";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import type { AdminUser, AdminUserStatus } from "@/lib/api/admin";

const STATUS_BADGE_VARIANT: Record<AdminUserStatus, "outline" | "destructive" | "secondary"> = {
  active: "outline",
  suspended: "destructive",
  pending_deletion: "secondary",
};

const STATUS_LABEL: Record<AdminUserStatus, string> = {
  active: "Active",
  suspended: "Suspended",
  pending_deletion: "Pending deletion",
};

/**
 * ui-ux.md §15 — "Table (user directory: email, plan, signup date,
 * status — no content columns, enforcing FR-ADMIN-001's explicit
 * exclusion of document/chat/extraction content)."
 */
export function AdminUserTable({ users }: { users: AdminUser[] }) {
  const [suspendTarget, setSuspendTarget] = useState<AdminUser | null>(null);
  const unsuspendMutation = useUnsuspendUserMutation();

  async function handleUnsuspend(user: AdminUser) {
    try {
      await unsuspendMutation.mutateAsync(user.id);
      toast.success(`${user.email} reinstated`);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't reinstate this account. Please try again.",
      );
    }
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Plan</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Signed up</TableHead>
            <TableHead className="w-24">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => (
            <TableRow key={user.id}>
              <TableCell className="font-medium">{user.email}</TableCell>
              <TableCell className="capitalize text-muted-foreground">{user.plan}</TableCell>
              <TableCell className="capitalize text-muted-foreground">{user.role}</TableCell>
              <TableCell>
                <Badge variant={STATUS_BADGE_VARIANT[user.status]}>
                  {STATUS_LABEL[user.status]}
                </Badge>
              </TableCell>
              <TableCell className="tabular-nums text-muted-foreground">
                {new Date(user.created_at).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })}
              </TableCell>
              <TableCell>
                {user.status === "suspended" ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => handleUnsuspend(user)}
                    disabled={unsuspendMutation.isPending}
                  >
                    {unsuspendMutation.isPending &&
                      unsuspendMutation.variables === user.id && (
                        <Loader2 className="animate-spin" aria-hidden="true" />
                      )}
                    Reinstate
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setSuspendTarget(user)}
                  >
                    Suspend
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <SuspendDialog
        userId={suspendTarget?.id ?? ""}
        email={suspendTarget?.email ?? ""}
        open={suspendTarget !== null}
        onOpenChange={(open) => {
          if (!open) setSuspendTarget(null);
        }}
      />
    </>
  );
}
