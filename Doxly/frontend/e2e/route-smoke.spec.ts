import { test, expect } from "@playwright/test";

/**
 * Phase 1 acceptance criterion: every placeholder route in the approved
 * route tree (specs/ui-ux.md §0, this repo's frontend plan §7) renders
 * without a runtime error. No session/auth guarding exists yet on
 * (dashboard) routes (deferred past Phase 2 — components/layout/top-bar.tsx
 * documents why), so those remain directly reachable here. /admin/* is the
 * one exception: Phase 15 wired a real role guard (AdminGuard) in front of
 * it, so those routes below assert the guard's rendered state, not raw
 * page content — see the dedicated /admin test below for detail.
 */

const staticRoutes = [
  "/",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/dashboard",
  "/documents",
  "/documents/upload",
  "/chat",
  "/extractions",
  "/compare",
  "/search",
  "/analytics",
  "/settings",
  "/admin/users",
  "/admin/system",
];

const dynamicRoutes = [
  "/documents/doc_test-id",
  "/chat/conv_test-id",
  "/extractions/ext_test-id",
  "/compare/cmp_test-id",
];

for (const route of [...staticRoutes, ...dynamicRoutes]) {
  test(`route ${route} responds 200 with no console errors`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    const response = await page.goto(route);
    expect(response?.status()).toBe(200);
    await expect(page.locator("body")).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });
}

/**
 * Phase 15 (Security Hardening) wired AdminGuard (security.md §3.1) in
 * front of every /admin/* route. It never renders `children` — and
 * therefore never mounts /admin's own redirect-to-/admin/users page —
 * until GET /users/me confirms role === "admin". Against the real
 * backend-less BFF that confirmation never arrives, so /admin now shows
 * the guard's "couldn't verify access" state and stays on /admin, per the
 * guard's documented fail-closed behavior. This intentionally supersedes
 * the pre-guard "always redirects" assumption; verifying the actual
 * redirect requires a real admin session, which this environment doesn't
 * have (same limitation as every other real-BFF-only E2E test in this
 * suite).
 */
test("/admin shows the access-verification gate, not a redirect, against an unreachable backend", async ({
  page,
}) => {
  await page.goto("/admin");
  await expect(page.getByText("We couldn't verify admin access right now.")).toBeVisible();
  await expect(page).toHaveURL(/\/admin$/);
});

test("unknown route renders the not-found page", async ({ page }) => {
  const response = await page.goto("/this-route-does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByText("Page not found")).toBeVisible();
});
