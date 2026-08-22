import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md's Phase 3 backend has no
 * documents router). Every request below hits the real BFF proxy
 * (app/api/v1/[...path]/route.ts), which genuinely 502s — these tests
 * exercise the real connectivity-error paths end-to-end, not a mock.
 */

test("documents list shows a real connectivity error and can retry", async ({ page }) => {
  await page.goto("/documents");

  await expect(
    page.getByText("We couldn't load your documents right now."),
  ).toBeVisible();

  const retry = page.getByRole("button", { name: "Try again" });
  await expect(retry).toBeVisible();
  await retry.click();
  await expect(
    page.getByText("We couldn't load your documents right now."),
  ).toBeVisible();
});

test("list/grid view toggle updates the URL and pressed state", async ({ page }) => {
  await page.goto("/documents");

  const gridButton = page.getByRole("button", { name: "Grid view" });
  await gridButton.click();
  await expect(page).toHaveURL(/view=grid/);
  await expect(gridButton).toHaveAttribute("aria-pressed", "true");

  const listButton = page.getByRole("button", { name: "List view" });
  await listButton.click();
  await expect(page).toHaveURL(/view=list/);
  await expect(listButton).toHaveAttribute("aria-pressed", "true");
});

test("upload dialog rejects an unsupported file client-side, with no network call", async ({
  page,
}) => {
  await page.goto("/documents");
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByRole("dialog", { name: "Upload documents" })).toBeVisible();

  const fixture = path.join(__dirname, "fixtures", "unsupported.zip");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(fixture);

  await expect(page.getByText(/unsupported file type/i)).toBeVisible();
  // Client-side rejection never reaches the network — no connectivity
  // error banner appears alongside it.
  await expect(
    page.getByText("We couldn't reach Doxly. Check your connection and try again."),
  ).not.toBeVisible();
});

test("upload dialog attempts a real upload and surfaces the connectivity error per file", async ({
  page,
}) => {
  await page.goto("/documents");
  await page.getByRole("button", { name: "Upload" }).click();

  const fixture = path.join(__dirname, "fixtures", "sample.pdf");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(fixture);

  await expect(page.getByText("sample.pdf")).toBeVisible();
  // presign() hits the real (backend-less) BFF proxy → genuine 502 →
  // upload-transport surfaces the shared connectivity message per row.
  await expect(
    page.getByText("We couldn't reach Doxly. Check your connection and try again."),
  ).toBeVisible();
});

test("document viewer for an unreachable backend shows the connectivity error, not a blank page", async ({
  page,
}) => {
  await page.goto("/documents/doc_test-id");

  await expect(
    page.getByText("We couldn't load this document right now."),
  ).toBeVisible();
  // Base UI's Button applies role="button" regardless of the underlying
  // element (same as the Google OAuth button in auth.spec.ts) — the
  // accessible role is "button," not "link," even though it renders <a>.
  await expect(page.getByRole("button", { name: "Back to Documents" })).toHaveAttribute(
    "href",
    "/documents",
  );
});

test("full-page upload route renders the same dropzone as the dialog", async ({ page }) => {
  await page.goto("/documents/upload");
  await expect(
    page.getByRole("button", { name: /drag files here/i }),
  ).toBeVisible();
});
