import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md's analytics router isn't built).
 * Every request below hits the real BFF proxy (app/api/v1/[...path]/route.ts),
 * which genuinely 502s — these tests exercise the real connectivity-error
 * paths end-to-end, not a mock.
 */

test("the analytics page shows a real connectivity error, not a blank dashboard", async ({ page }) => {
  await page.goto("/analytics");

  await expect(page.getByText("We couldn't load your analytics right now.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("the period selector is usable even while the dashboard can't load", async ({ page }) => {
  await page.goto("/analytics");

  const ninetyDays = page.getByRole("button", { name: "90 days" });
  await expect(ninetyDays).toBeVisible();
  await ninetyDays.click();
  await expect(ninetyDays).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/period=90d/);
});
