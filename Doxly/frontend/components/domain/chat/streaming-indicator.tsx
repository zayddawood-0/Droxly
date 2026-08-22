/**
 * ui-ux.md §8 — "subtle animated dots/cursor, not a full spinner that
 * hides partial content" — rendered inline after already-streamed text,
 * never replacing it. Respects prefers-reduced-motion via the shared
 * animate-pulse utility already used elsewhere (status-badge.tsx).
 */
export function StreamingIndicator() {
  return (
    <span
      className="ml-0.5 inline-flex items-center gap-0.5 align-middle"
      role="status"
      aria-label="Generating response"
    >
      <span className="size-1 animate-pulse rounded-full bg-current opacity-60 motion-reduce:animate-none" />
      <span className="size-1 animate-pulse rounded-full bg-current opacity-60 [animation-delay:150ms] motion-reduce:animate-none" />
      <span className="size-1 animate-pulse rounded-full bg-current opacity-60 [animation-delay:300ms] motion-reduce:animate-none" />
    </span>
  );
}
