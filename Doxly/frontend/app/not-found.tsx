import Link from "next/link";
import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Global 404 — also the response surface for cross-tenant access attempts
 * once real resource routes exist (specs/security.md §3.2: "404, not 403" —
 * a foreign resource must render identically to a nonexistent one).
 */
export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <FileQuestion className="size-10 text-muted-foreground" aria-hidden="true" />
      <div>
        <h1 className="text-xl font-bold">Page not found</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          This page doesn&apos;t exist, or you don&apos;t have access to it.
        </p>
      </div>
      <Button nativeButton={false} render={<Link href="/dashboard" />}>
        Back to Dashboard
      </Button>
    </div>
  );
}
