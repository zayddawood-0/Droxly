"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Both light and dark mode are baseline requirements (specs/ui-ux.md §15), not a
 * toggle-if-you-feel-like-it. Default follows the OS preference; a manual override
 * lives in Settings → Appearance (wired in a later phase) and persists via the
 * "theme" localStorage key next-themes manages.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
