import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md's comparisons router isn't
 * built). Every request below hits the real BFF proxy
 * (app/api/v1/[...path]/route.ts), which genuinely 502s — these tests
 * exercise the real connectivity-error paths end-to-end, not a mock.
 */

test("the compare page shows connectivity errors for the document pickers and history, not blank sections", async ({
  page,
}) => {
  await page.goto("/compare");

  await expect(page.getByText("Couldn't load past comparisons.")).toBeVisible();

  await page.getByRole("button", { name: /select the first document/i }).click();
  await expect(page.getByText("Couldn't load your documents.")).toBeVisible();
});

test("comparison report page for an unreachable comparison shows the connectivity error, not a blank page", async ({
  page,
}) => {
  await page.goto("/compare/cmp_test-id");

  await expect(
    page.getByText("We couldn't load this comparison right now."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Back to Compare" })).toBeVisible();
});
