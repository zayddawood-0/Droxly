import { test, expect } from "@playwright/test";

/**
 * Regression coverage for a bug found during Phase 1 visual QA: Base UI's
 * Menu.GroupLabel throws ("MenuGroupContext is missing") when used outside a
 * Menu.Group, unlike Radix's DropdownMenuLabel which tolerates standalone
 * use — the mismatch crashed the renderer the moment the account menu
 * opened. Fixed by wrapping DropdownMenuLabel in DropdownMenuGroup
 * (components/layout/top-bar.tsx).
 */
test("account menu opens without crashing and shows Settings", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Open account menu" }).click();

  await expect(page.getByRole("menuitem", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Log out" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("mobile nav sheet opens and lists every primary destination", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Open navigation menu" }).click();

  for (const label of [
    "Dashboard",
    "Documents",
    "AI Chat",
    "Extractions",
    "Compare",
    "Search",
    "Analytics",
    "Settings",
  ]) {
    await expect(
      page.getByRole("link", { name: label, exact: true }),
    ).toBeVisible();
  }
});
