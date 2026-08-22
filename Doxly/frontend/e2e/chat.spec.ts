import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md's chat router isn't built).
 * Every request below hits the real BFF proxy (app/api/v1/[...path]/route.ts),
 * which genuinely 502s — these tests exercise the real connectivity-error
 * paths end-to-end, not a mock, matching this track's established pattern.
 */

test("new chat page renders the composer and scope picker", async ({ page }) => {
  await page.goto("/chat");

  await expect(page.getByRole("textbox", { name: "Message" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  await expect(page.getByRole("button", { name: /all documents/i })).toBeVisible();
});

test("sending a message on the real backend-less BFF surfaces the connectivity error", async ({
  page,
}) => {
  await page.goto("/chat");

  await page.getByRole("textbox", { name: "Message" }).fill("What is the revenue?");
  await page.getByRole("button", { name: "Send message" }).click();

  // createConversation() hits the real (backend-less) BFF → genuine 502 →
  // send() rejects before any optimistic message ever appears.
  await expect(
    page.getByText("We couldn't reach Doxly. Check your connection and try again."),
  ).toBeVisible({ timeout: 10_000 });
});

test("conversation list shows a real connectivity error, not a blank sidebar", async ({
  page,
}) => {
  await page.goto("/chat");
  await expect(page.getByText("Couldn't load your conversations.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("an unreachable conversation shows the connectivity error, not a blank thread", async ({
  page,
}) => {
  await page.goto("/chat/conv_test-id");
  await expect(
    page.getByText("We couldn't load this conversation right now."),
  ).toBeVisible();
});

test("mobile viewport collapses the conversation list into a drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/chat");

  await expect(page.getByRole("button", { name: "Open conversation list" })).toBeVisible();
  await page.getByRole("button", { name: "Open conversation list" }).click();
  // The drawer itself is the signal — ConversationList also renders its
  // own "Conversations" heading, which combined with the dialog's
  // (sr-only) accessible title would otherwise make a heading-text
  // assertion here ambiguous.
  await expect(page.getByRole("dialog")).toBeVisible();
});
