"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { primaryNavItems, settingsNavItem } from "@/lib/nav-items";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Persistent left sidebar, per specs/ui-ux.md §0 — exact nav order/labels from
 * lib/nav-items.ts. Full labeled rail at `lg`+, collapses to an icon-only rail
 * at `md` ("collapsible on tablet"), hidden below `md` where MobileNav takes
 * over ("replaced by a bottom/hamburger nav on mobile").
 *
 * Active route uses a filled icon/label + accent text, not a heavy background
 * block, per ui-ux.md §0's explicit "not a heavy background block" rule.
 */
export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "hidden md:flex md:w-16 lg:w-60 md:flex-col md:shrink-0",
        "border-r border-sidebar-border bg-sidebar text-sidebar-foreground",
        "h-dvh sticky top-0",
      )}
    >
      <div className="flex h-14 items-center gap-2 px-4 lg:px-5 border-b border-sidebar-border">
        <Sparkles className="size-5 shrink-0 text-primary" aria-hidden="true" />
        <span className="hidden lg:inline font-heading font-extrabold text-[15px] tracking-tight">
          Doxly
        </span>
      </div>

      <nav
        aria-label="Primary"
        className="flex-1 overflow-y-auto py-3 px-2 lg:px-3 flex flex-col gap-0.5"
      >
        {primaryNavItems.map((item) => (
          <SidebarLink
            key={item.href}
            item={item}
            active={isActive(pathname, item.href)}
          />
        ))}
      </nav>

      <div className="border-t border-sidebar-border py-3 px-2 lg:px-3">
        <SidebarLink
          item={settingsNavItem}
          active={isActive(pathname, settingsNavItem.href)}
        />
      </div>
    </aside>
  );
}

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function SidebarLink({
  item,
  active,
}: {
  item: (typeof primaryNavItems)[number];
  active: boolean;
}) {
  const Icon = item.icon;

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Link
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors",
              "lg:justify-start justify-center",
              active
                ? "text-primary font-medium bg-sidebar-accent"
                : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/60",
            )}
          />
        }
      >
        <Icon
          className="size-[18px] shrink-0"
          strokeWidth={active ? 2.25 : 1.75}
          aria-hidden="true"
        />
        <span className="hidden lg:inline">{item.label}</span>
      </TooltipTrigger>
      <TooltipContent side="right" className="lg:hidden">
        {item.label}
      </TooltipContent>
    </Tooltip>
  );
}
