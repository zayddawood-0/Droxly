import type { ReactNode } from "react";
import { AdminGuard } from "@/components/layout/admin-guard";

// Role guard (role="admin", specs/security.md §3.1) — wired in Phase 15.
// AdminGuard fetches GET /users/me and only renders AdminShell/children once
// role === "admin" is confirmed; every other outcome (pending, error, wrong
// role) renders its own state and never mounts the shell.
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminGuard>{children}</AdminGuard>;
}
