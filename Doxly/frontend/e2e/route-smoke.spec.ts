import { test, expect } from "@playwright/test";

/**
 * Phase 1 acceptance criterion: every placeholder route in the approved
 * route tree (specs/ui-ux.md §0, this repo's frontend plan §7) renders
 * without a runtime error. No auth/data guarding exists yet (Phase 2+), so
 * every route is reachable directly in this phase.
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

test("/admin redirects to /admin/users", async ({ page }) => {
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/users$/);
});

test("unknown route renders the not-found page", async ({ page }) => {
  const response = await page.goto("/this-route-does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByText("Page not found")).toBeVisible();
});
