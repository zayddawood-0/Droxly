import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md's extractions router isn't
 * built). Every request below hits the real BFF proxy
 * (app/api/v1/[...path]/route.ts), which genuinely 502s — these tests
 * exercise the real connectivity-error paths end-to-end, not a mock.
 */

test("extractions page prompts for a document when none is pre-selected", async ({ page }) => {
  await page.goto("/extractions");

  await expect(page.getByText("Choose a document to extract from")).toBeVisible();
  await expect(page.getByRole("button", { name: /select a document/i })).toBeVisible();
});

test("the document picker shows a real connectivity error, not a blank popover", async ({ page }) => {
  await page.goto("/extractions");

  await page.getByRole("button", { name: /select a document/i }).click();
  await expect(page.getByText("Couldn't load your documents.")).toBeVisible();
});

test("a pre-selected document shows connectivity errors for history and templates, not blank sections", async ({
  page,
}) => {
  await page.goto("/extractions?document=doc_test-id");

  await expect(page.getByText("Couldn't load past extractions.")).toBeVisible();
  await expect(page.getByText("Couldn't load extraction templates.")).toBeVisible();
});

test("extraction results page for an unreachable extraction shows the connectivity error, not a blank page", async ({
  page,
}) => {
  await page.goto("/extractions/ext_test-id");

  await expect(
    page.getByText("We couldn't load this extraction right now."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Back to Extractions" })).toBeVisible();
});

