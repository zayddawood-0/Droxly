import { useEffect, useState } from "react";

/** Global Search's "debounced query-as-you-type" (ui-ux.md §12, FR-SEARCH-001). */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
