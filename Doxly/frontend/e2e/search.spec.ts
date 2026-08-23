import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md's search router isn't built).
 * Every request below hits the real BFF proxy (app/api/v1/[...path]/route.ts),
 * which genuinely 502s — these tests exercise the real connectivity-error
 * paths end-to-end, not a mock.
 */

test("the search page shows the no-query empty state with example queries", async ({ page }) => {
  await page.goto("/search");

  await expect(page.getByText("Search across all your documents")).toBeVisible();
  await expect(page.getByRole("button", { name: "termination clause" })).toBeVisible();
});

test("submitting a query shows a real connectivity error, not a blank results region", async ({
  page,
}) => {
  await page.goto("/search");

  await page.getByRole("textbox", { name: "Search documents" }).fill("revenue");
  await expect(page.getByText("We couldn't load results right now.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("clicking an example query fills the input and searches", async ({ page }) => {
  await page.goto("/search");

  await page.getByRole("button", { name: "Q3 revenue" }).click();
  await expect(page.getByRole("textbox", { name: "Search documents" })).toHaveValue("Q3 revenue");
  await expect(page.getByText("We couldn't load results right now.")).toBeVisible();
});

test("the global search trigger and Ctrl+K both navigate to /search", async ({ page }) => {
  await page.goto("/dashboard");

  await page.keyboard.press("Control+k");
  await expect(page).toHaveURL(/\/search$/);

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Open global search" }).first().click();
  await expect(page).toHaveURL(/\/search$/);
});
