"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Server-state layer (skills/frontend.md §10): caching, revalidation, and
 * loading/error state for documents/tags without hand-rolled useEffect
 * fetch boilerplate. One QueryClient per browser session — created inside
 * the component (not module scope) so it isn't shared across requests
 * during SSR.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
