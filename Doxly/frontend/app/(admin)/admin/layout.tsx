import type { ReactNode } from "react";
import { AdminShell } from "@/components/layout/admin-shell";

// Role guard (role="admin", specs/security.md §3.1) is wired in Phase 2/15
// alongside real session data — this layout only establishes the shell.
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
