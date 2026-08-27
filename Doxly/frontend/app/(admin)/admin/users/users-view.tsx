"use client";

import { useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { AdminUserTable } from "@/components/domain/admin/admin-user-table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAdminUsersQuery } from "@/hooks/use-admin";
import type { AdminUserPlan, AdminUserStatus } from "@/lib/api/admin";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: AdminUserStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
  { value: "pending_deletion", label: "Pending deletion" },
];

const PLAN_OPTIONS: { value: AdminUserPlan | "all"; label: string }[] = [
  { value: "all", label: "All plans" },
  { value: "free", label: "Free" },
  { value: "pro", label: "Pro" },
];

/**
 * ui-ux.md §15 — user directory: status/plan filters (api.md §12's real
 * query params), an email search that narrows the currently-loaded page
 * client-side (api.md §12 defines no server-side email search param — the
 * same client-side-over-the-loaded-page pattern DocumentsView already uses
 * for its own filename search).
 */
export function AdminUsersView() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const search = searchParams.get("search") ?? "";
  const status = (searchParams.get("status") as AdminUserStatus | null) ?? "all";
  const plan = (searchParams.get("plan") as AdminUserPlan | null) ?? "all";
  const page = Number(searchParams.get("page") ?? "0");

  const updateParams = useCallback(
    (patch: { search?: string; status?: string; plan?: string; page?: number }) => {
      const next = new URLSearchParams(searchParams.toString());
      const merged = { search, status, plan, ...patch };

      if (merged.search) next.set("search", merged.search);
      else next.delete("search");
      if (merged.status !== "all") next.set("status", merged.status);
      else next.delete("status");
      if (merged.plan !== "all") next.set("plan", merged.plan);
      else next.delete("plan");

      if (patch.page !== undefined) next.set("page", String(patch.page));
      else next.delete("page");

      router.replace(`/admin/users?${next.toString()}`, { scroll: false });
    },
    [search, status, plan, router, searchParams],
  );

  const query = useAdminUsersQuery({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    status: status === "all" ? undefined : status,
    plan: plan === "all" ? undefined : plan,
  });

  const visibleUsers = useMemo(() => {
    const items = query.data?.items ?? [];
    if (!search) return items;
    const needle = search.toLowerCase();
    return items.filter((user) => user.email.toLowerCase().includes(needle));
  }, [query.data, search]);

  const totalPages = query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0;

  return (
    <>
      <PageHeader
        title="Users"
        description="Account/operational metadata only — never document, chat, or extraction content."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="relative flex-1 sm:max-w-64">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(event) => updateParams({ search: event.target.value })}
            placeholder="Search by email…"
            className="pl-8"
            aria-label="Search users by email"
          />
        </div>
        <Select value={status} onValueChange={(value) => updateParams({ status: value ?? "all" })}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={plan} onValueChange={(value) => updateParams({ plan: value ?? "all" })}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PLAN_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-4">
        {query.isPending ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : query.isError ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-danger/40 bg-danger-soft/40 px-6 py-16 text-center">
            <p className="text-sm text-muted-foreground">
              We couldn&apos;t load the user directory right now.
            </p>
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Try again
            </Button>
          </div>
        ) : visibleUsers.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-6 py-16 text-center">
            <p className="text-sm font-medium">No users match these filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <AdminUserTable users={visibleUsers} />
          </div>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => updateParams({ page: page - 1 })}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground tabular-nums">
              Page {page + 1} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= totalPages}
              onClick={() => updateParams({ page: page + 1 })}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </>
  );
}
