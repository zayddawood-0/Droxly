import type { ReactNode } from "react";
import { PageShell } from "@/components/layout/page-shell";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <PageShell>{children}</PageShell>;
}
