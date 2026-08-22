import type { ReactNode } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";

/**
 * Minimal-chrome auth layout (specs/ui-ux.md §2/§3): a centered card on a
 * plain background, no marketing nav, no app sidebar.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-background px-4 py-10">
      <Link
        href="/"
        className="mb-8 flex items-center gap-2 text-foreground no-underline"
      >
        <Sparkles className="size-5 text-primary" aria-hidden="true" />
        <span className="font-heading text-lg font-extrabold tracking-tight">
          Doxly
        </span>
      </Link>
      <div className="w-full max-w-[400px]">{children}</div>
    </div>
  );
}
