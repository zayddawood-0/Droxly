import path from "node:path";
import type { NextConfig } from "next";

/**
 * specs/security.md §11.3 (NFR-SEC-011) — security headers applied on every
 * response from the Next.js frontend.
 *
 * `script-src`/`style-src` include 'unsafe-inline' — a deliberate,
 * documented trade-off, not an oversight. A per-request nonce (Next.js 16's
 * documented Proxy-based CSP pattern — see node_modules/next/dist/docs/.../
 * file-conventions/proxy.md) was implemented and verified working under
 * `next dev`, but failed under this project's actual production
 * configuration (`output: "standalone"` + Turbopack, `next build && next
 * start`): several of Next.js's own static `<script src>` tags in the
 * production HTML are not nonce-stamped, so a nonce'd `script-src` blocks
 * the app's own hydration scripts and the app never becomes interactive.
 * This reproduced consistently across multiple rebuilds — not a one-off
 * flake — so shipping it would trade a broken app for an untested security
 * gain. Tracked as decisions.md OQ-12 for revisit once Next.js's
 * Proxy-nonce support stabilizes for this build configuration.
 *
 * The residual risk of 'unsafe-inline' here is low in this specific app:
 * the XSS audit performed alongside this change (grep for
 * dangerouslySetInnerHTML across the whole frontend) found exactly one use
 * (components/ui/chart.tsx), and its content is always this app's own
 * static config — never document- or user-derived — so there is no known
 * code path today that would let an attacker get their own inline <script>
 * onto the page even with this directive relaxed. Every other directive
 * stays fully restrictive: no external script/style/image/font/connect
 * origins, no framing, no plugin objects.
 *
 * `'unsafe-eval'` is added to `script-src` in development only — React's
 * dev-mode debugging tools (callstack reconstruction) call `eval()` and
 * are blocked without it (confirmed via a real browser: the console shows
 * "React requires eval() in development mode..."). React's own message is
 * explicit that "React will never use eval() in production mode," and this
 * project's production build (`next build && next start`, the same
 * configuration `playwright.config.ts` and the Dockerfile use) was
 * verified clean without it — so this is a dev-ergonomics allowance, never
 * a production security relaxation.
 */
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // Pins the workspace root to this directory so Turbopack doesn't walk up
  // into the user's home directory looking for a lockfile (a stray, unrelated
  // package-lock.json can otherwise exist above the repo on a given machine).
  turbopack: {
    root: path.join(__dirname),
  },
  // Produces a minimal, self-contained server bundle (only the production
  // deps actually reachable at runtime) — what the Dockerfile's runtime
  // stage copies, per skills/devops.md's "keep the image lean" guidance.
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;
