import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Landing page — deliberately a minimal shell for Phase 1 (specs/roadmap.md
 * Phase 1's own expected output: "empty landing page shell"). The full
 * marketing build (hero visuals, feature grid, CTA band, footer per
 * specs/ui-ux.md §1) is unscoped work with no owning roadmap phase or
 * requirement ID — building it now would be scope creep beyond this task's
 * P01-001..005 list, not a blocked dependency.
 */
export default function LandingPage() {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="flex h-16 items-center justify-between px-6 md:px-10">
        <div className="flex items-center gap-2">
          <Sparkles className="size-5 text-primary" aria-hidden="true" />
          <span className="font-heading text-lg font-extrabold tracking-tight">
            Doxly
          </span>
        </div>
        <nav className="flex items-center gap-2">
          <Button variant="ghost" nativeButton={false} render={<Link href="/login" />}>
            Log in
          </Button>
          <Button nativeButton={false} render={<Link href="/register" />}>
            Sign up
          </Button>
        </nav>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="max-w-xl text-4xl font-extrabold tracking-tight text-balance md:text-5xl">
          Your docs, but smarter.
        </h1>
        <p className="mt-4 max-w-md text-base text-muted-foreground">
          Upload → Understand → Ask → Extract → Compare → Search → Act.
        </p>
        <div className="mt-8 flex gap-3">
          <Button size="lg" nativeButton={false} render={<Link href="/register" />}>
            Get started
          </Button>
          <Button
            size="lg"
            variant="outline"
            nativeButton={false}
            render={<Link href="/login" />}
          >
            Log in
          </Button>
        </div>
      </main>

      <footer className="px-6 py-6 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} Doxly
      </footer>
    </div>
  );
}
