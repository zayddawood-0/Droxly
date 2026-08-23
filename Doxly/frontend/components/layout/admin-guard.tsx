"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AdminShell } from "@/components/layout/admin-shell";
import { useCurrentUserQuery } from "@/hooks/use-current-user";

/**
 * specs/security.md §3.1 — role check for every `/admin/*` route: "does the
 * caller's role permit this endpoint at all." §0.4/api.md's route table
 * marks `/admin/*` as the one deliberate exception to the "404, not 403"
 * pattern (§3.2) — this guard shows a genuine "you don't have permission"
 * message for a non-admin caller, never a 404, since role checks (unlike
 * resource-ownership checks) aren't existence-sensitive information.
 *
 * Fails closed: a caller whose role can't be verified (query error) never
 * sees the admin shell or its children — an unreachable `/users/me` is
 * treated the same as "not confirmed admin," not "assume admin."
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const query = useCurrentUserQuery();

  if (query.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-muted/40">
        <p className="text-sm text-muted-foreground">Verifying access…</p>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-muted/40 px-6 text-center">
        <ShieldAlert className="size-6 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">We couldn&apos;t verify admin access right now.</p>
        <Button variant="outline" size="sm" onClick={() => query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  if (query.data.role !== "admin") {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-muted/40 px-6 text-center">
        <ShieldAlert className="size-6 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium">You don&apos;t have permission to view this page.</p>
        <Button variant="outline" size="sm" render={<Link href="/dashboard" />} nativeButton={false}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  return <AdminShell>{children}</AdminShell>;
}
