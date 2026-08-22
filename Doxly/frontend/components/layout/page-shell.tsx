import type { ReactNode } from "react";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { TopBar } from "@/components/layout/top-bar";

/**
 * The authenticated app shell wrapping every (dashboard) route: persistent
 * sidebar + top bar + content region (specs/ui-ux.md §0). A Server Component —
 * it holds no state itself; AppSidebar/TopBar are the client islands that need
 * pathname/interactivity, kept as small as possible per skills/frontend.md §2.
 */
export function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh w-full">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 px-4 py-6 md:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
