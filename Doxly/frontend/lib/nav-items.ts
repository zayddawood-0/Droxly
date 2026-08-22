import type { LucideIcon } from "lucide-react";
import {
  House,
  Files,
  Sparkles,
  FileSearch,
  ArrowLeftRight,
  Search,
  BarChart3,
  Settings,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

/**
 * Single source of truth for the primary nav, transcribed verbatim from
 * specs/ui-ux.md §0 — unchanged order, unchanged label set. AppSidebar and
 * MobileNav both render from this list so the two surfaces can never drift.
 */
export const primaryNavItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: House },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/chat", label: "AI Chat", icon: Sparkles },
  { href: "/extractions", label: "Extractions", icon: FileSearch },
  { href: "/compare", label: "Compare", icon: ArrowLeftRight },
  { href: "/search", label: "Search", icon: Search },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

export const settingsNavItem: NavItem = {
  href: "/settings",
  label: "Settings",
  icon: Settings,
};
