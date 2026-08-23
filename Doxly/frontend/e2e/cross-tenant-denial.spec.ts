import { test, expect } from "@playwright/test";

/**
 * testing.md §2.4 — "a cross-tenant denial surfaced correctly in the UI
 * (e.g., navigating to another user's document URL shows a not-found
 * state, never a broken/leaked page)" — named explicitly as a required
 * secondary E2E flow, distinct from the general connectivity-error paths
 * every other spec in this directory exercises against the real
 * backend-less BFF (which can only ever 502, never a real 404).
 *
 * Every detail route already handles this correctly per the security.md
 * §3.2 "404, not 403" pattern (verified once already at the component
 * level with MSW in each domain's *.test.tsx — see e.g.
 * extraction-results-view.test.tsx, comparison-report-view.test.tsx,
 * chat-thread.test.tsx). This spec is the one place that same behavior is
 * proven end-to-end through a real browser rendering the real page, by
 * mocking the BFF proxy response at the network layer (`page.route`)
 * rather than relying on the (currently always-502) live backend.
 */

const notFoundBody = { error: { code: "not_found", message: "Not found." } };

test("a foreign/nonexistent document shows a clean not-found state, never a broken page", async ({ page }) => {
  await page.route("**/api/v1/documents/doc_other-tenant", (route) =>
    route.fulfill({ status: 404, json: notFoundBody }),
  );

  await page.goto("/documents/doc_other-tenant");

  await expect(
    page.getByText("This document doesn't exist, or you don't have access to it."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).not.toBeVisible();
});

test("a foreign/nonexistent conversation shows a clean not-found state, never a broken page", async ({ page }) => {
  // The sidebar's ConversationList fires its own, separate request
  // (GET /chat/conversations, the list) — mocked to a real empty result so
  // its own connectivity-error UI doesn't produce an unrelated second "Try
  // again" button and mask what this test actually asserts about the
  // active-thread pane.
  await page.route("**/api/v1/chat/conversations?*", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }),
  );
  await page.route("**/api/v1/chat/conversations/conv_other-tenant", (route) =>
    route.fulfill({ status: 404, json: notFoundBody }),
  );

  await page.goto("/chat/conv_other-tenant");

  await expect(
    page.getByText("This conversation doesn't exist, or you don't have access to it."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).not.toBeVisible();
});

test("a foreign/nonexistent extraction shows a clean not-found state, never a broken page", async ({ page }) => {
  await page.route("**/api/v1/extractions/ext_other-tenant", (route) =>
    route.fulfill({ status: 404, json: notFoundBody }),
  );

  await page.goto("/extractions/ext_other-tenant");

  await expect(
    page.getByText("This extraction doesn't exist, or you don't have access to it."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).not.toBeVisible();
});

test("a foreign/nonexistent comparison shows a clean not-found state, never a broken page", async ({ page }) => {
  await page.route("**/api/v1/comparisons/cmp_other-tenant", (route) =>
    route.fulfill({ status: 404, json: notFoundBody }),
  );

  await page.goto("/compare/cmp_other-tenant");

  await expect(
    page.getByText("This comparison doesn't exist, or you don't have access to it."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).not.toBeVisible();
});
