"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { primaryNavItems, settingsNavItem } from "@/lib/nav-items";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/**
 * Mobile replacement for AppSidebar (specs/ui-ux.md §0: "replaced by a
 * bottom/hamburger nav on mobile"). A hamburger trigger opens a full nav list
 * in a Sheet rather than a cramped bottom tab bar — with 8 destinations
 * (7 primary + Settings), a bottom bar would either crowd or silently drop
 * items; the spec names "hamburger" as an accepted alternative.
 */
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open navigation menu"
          />
        }
      >
        <Menu className="size-5" aria-hidden="true" />
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader className="border-b border-border px-4 py-3.5">
          <SheetTitle className="flex items-center gap-2 font-heading text-[15px]">
            <Sparkles className="size-5 text-primary" aria-hidden="true" />
            Doxly
          </SheetTitle>
        </SheetHeader>
        <nav aria-label="Primary" className="flex flex-col gap-0.5 p-2">
          {primaryNavItems.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm",
                  active
                    ? "text-primary font-medium bg-accent"
                    : "text-foreground/80 hover:bg-accent/60",
                )}
              >
                <Icon className="size-[18px]" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
          <div className="my-1 border-t border-border" />
          <Link
            href={settingsNavItem.href}
            onClick={() => setOpen(false)}
            className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm text-foreground/80 hover:bg-accent/60"
          >
            <settingsNavItem.icon className="size-[18px]" aria-hidden="true" />
            {settingsNavItem.label}
          </Link>
        </nav>
      </SheetContent>
    </Sheet>
  );
}
