import type { ReactNode } from "react";
import Link from "next/link";
import { ShieldAlert, Users, Activity } from "lucide-react";

/**
 * Internal operational tooling shell (specs/ui-ux.md §14) — deliberately NOT
 * the consumer AppSidebar. A left tab set (Users, System Health) with muted,
 * utility-grade chrome so /admin never reads as a "power user" area of the
 * consumer product. Reached only by a role-guarded route (role check wired in
 * Phase 2/15), never linked from the standard sidebar.
 */
const adminTabs = [
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/system", label: "System Health", icon: Activity },
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-muted/40">
      <header className="flex h-12 items-center gap-2 border-b border-border bg-secondary px-4 text-secondary-foreground">
        <ShieldAlert className="size-4" aria-hidden="true" />
        <span className="font-mono text-xs uppercase tracking-wider">
          Doxly — Internal Admin
        </span>
      </header>
      <div className="flex">
        <nav
          aria-label="Admin sections"
          className="w-48 shrink-0 border-r border-border p-3"
        >
          {adminTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground/75 hover:bg-secondary hover:text-foreground"
              >
                <Icon className="size-4" aria-hidden="true" />
                {tab.label}
              </Link>
            );
          })}
        </nav>
        <main className="min-w-0 flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
