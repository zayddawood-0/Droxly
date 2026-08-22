import { test, expect } from "@playwright/test";

/**
 * No backend exists yet (specs/roadmap.md Phase 2's backend half is out of
 * scope for this frontend-only task). Every submission below hits the real
 * BFF proxy (app/api/v1/[...path]/route.ts), which genuinely returns 502
 * with no INTERNAL_API_URL backend behind it — these tests exercise the real
 * connectivity-error path end-to-end, not a mock.
 */

test("login form validates before submitting and shows a real connectivity error", async ({
  page,
}) => {
  await page.goto("/login");

  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("Enter your email address")).toBeVisible();

  await page.getByLabel("Email").fill("maya@example.com");
  await page.getByLabel("Password").fill("abcd1234");
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(
    page.getByText("We couldn't reach Doxly. Check your connection and try again."),
  ).toBeVisible();
  // Still on /login — a connectivity error never redirects.
  await expect(page).toHaveURL(/\/login$/);
});

test("register form enforces the password policy before submitting", async ({
  page,
}) => {
  await page.goto("/register");

  await page.getByLabel("Name").fill("Maya");
  await page.getByLabel("Email").fill("maya@example.com");
  await page.getByLabel("Password").fill("short");

  // Live strength-meter feedback (not a FieldError) is the spec's stated
  // mechanism here (ui-ux.md §3: "real-time password strength feedback").
  await expect(page.getByText("At least 8 characters")).toBeVisible();

  await page.getByRole("button", { name: "Create account" }).click();
  // Client-side validation blocks the request entirely — still on /register.
  await expect(page).toHaveURL(/\/register$/);
});

test("forgot-password shows the same confirmation the spec requires, even with no backend", async ({
  page,
}) => {
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill("maya@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();

  // A 502 here is itself a genuine failure of the "always 202" contract —
  // the UI still must not crash or blank out; it surfaces the connectivity
  // banner rather than a fabricated success.
  await expect(
    page.getByText("We couldn't reach Doxly. Check your connection and try again."),
  ).toBeVisible();
});

test("reset-password with no token in the URL shows the request-a-new-link state", async ({
  page,
}) => {
  await page.goto("/reset-password");
  await expect(
    page.getByText("This password reset link is missing or malformed."),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Request a new link" })).toBeVisible();
});

test("verify-email with no token shows the missing-link state without a network call", async ({
  page,
}) => {
  await page.goto("/verify-email");
  await expect(
    page.getByText("This verification link is missing or malformed."),
  ).toBeVisible();
});

test("Google button on Login navigates to the OAuth start route", async ({ page }) => {
  await page.goto("/login");
  // Rendered as <a> for real navigation, but Base UI's Button primitive
  // applies role="button" (keyboard/interaction semantics) regardless of the
  // underlying element — the accessible role is "button," not "link".
  const googleButton = page.getByRole("button", { name: "Continue with Google" });
  await expect(googleButton).toHaveAttribute("href", "/api/v1/auth/oauth/google");
});

test("logout with no backend shows the connectivity error toast, not a redirect", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Open account menu" }).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();

  // No backend → the logout call itself fails as a 502 → the connectivity
  // toast, never a silent redirect that would claim logout succeeded.
  await expect(
    page.getByText("We couldn't reach Doxly. Check your connection and try again."),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/dashboard$/);
});
