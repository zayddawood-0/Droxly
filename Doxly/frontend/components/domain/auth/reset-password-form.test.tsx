import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { mswServer } from "@/lib/test/msw-server";
import { ResetPasswordForm } from "./reset-password-form";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

beforeEach(() => pushMock.mockClear());

describe("ResetPasswordForm — FR-AUTH-007", () => {
  it("shows a 'request a new link' state when no token is present in the URL", () => {
    render(<ResetPasswordForm token={undefined} />);
    expect(
      screen.getByText("This password reset link is missing or malformed."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new link" })).toBeInTheDocument();
  });

  it("redirects to login on a successful reset", async () => {
    mswServer.use(
      http.post("/api/v1/auth/password-reset/confirm", () =>
        HttpResponse.json({ reset: true }),
      ),
    );

    const user = userEvent.setup();
    render(<ResetPasswordForm token="valid-token" />);
    await user.type(screen.getByLabelText("New password"), "abcd1234");
    await user.type(screen.getByLabelText("Confirm new password"), "abcd1234");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
  });

  it("shows an expired-link message on an invalid token, not a field error", async () => {
    mswServer.use(
      http.post("/api/v1/auth/password-reset/confirm", () =>
        HttpResponse.json(
          { error: { code: "invalid_or_expired_token", message: "..." } },
          { status: 400 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(<ResetPasswordForm token="expired-token" />);
    await user.type(screen.getByLabelText("New password"), "abcd1234");
    await user.type(screen.getByLabelText("Confirm new password"), "abcd1234");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(
      await screen.findByText(/this link has expired or is no longer valid/i),
    ).toBeInTheDocument();
  });
});
