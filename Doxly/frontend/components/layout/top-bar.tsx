"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, User, Settings, LogOut } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { MobileNav } from "@/components/layout/mobile-nav";
import { logout } from "@/lib/api/auth";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

/**
 * Global top bar, present on every authenticated page (specs/ui-ux.md §0):
 * a command/search trigger and a user menu. Logout (FR-AUTH-006) is wired to
 * the real endpoint. The account menu does not yet show the real signed-in
 * identity — that needs GET /users/me, deferred to the phase that gives
 * Dashboard real session-aware content, per this phase's documented scope
 * boundary (tasks/02-authentication-ui.md). Routes under (dashboard)/(admin)
 * are also not gated on a session yet, for the same reason: no backend
 * exists yet to authenticate against, and gating now would make every
 * existing placeholder route unreachable in dev.
 */
export function TopBar() {
  const router = useRouter();

  async function handleLogout() {
    try {
      await logout();
      router.push("/login");
      router.refresh();
    } catch (error) {
      // Error toasts persist until dismissed (specs/ui-ux.md §15) — never
      // auto-dismiss a failure the user hasn't acknowledged.
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't log out. Please try again.",
        { duration: Infinity },
      );
    }
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/80 md:px-5">
      <MobileNav />

      <div className="flex-1" />

      <Button
        variant="outline"
        size="sm"
        className="hidden sm:flex items-center gap-2 text-muted-foreground font-normal"
        aria-label="Open global search"
      >
        <Search className="size-4" aria-hidden="true" />
        <span>Search documents…</span>
        <kbd className="ml-2 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          ⌘K
        </kbd>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="sm:hidden"
        aria-label="Open global search"
      >
        <Search className="size-[18px]" aria-hidden="true" />
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="rounded-full"
              aria-label="Open account menu"
            />
          }
        >
          <Avatar className="size-8">
            <AvatarFallback className="bg-accent text-accent-foreground text-xs">
              <User className="size-4" aria-hidden="true" />
            </AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {/* Base UI requires GroupLabel to live inside a Menu.Group — unlike
              Radix, a bare label crashes at runtime, not just a lint warning. */}
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
              Account
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem render={<Link href="/settings" />}>
            <Settings className="size-4" aria-hidden="true" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleLogout}>
            <LogOut className="size-4" aria-hidden="true" />
            Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
