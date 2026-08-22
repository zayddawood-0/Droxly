import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { mswServer } from "@/lib/test/msw-server";
import { ForgotPasswordForm } from "./forgot-password-form";

describe("ForgotPasswordForm — FR-AUTH-007", () => {
  it("shows the same confirmation regardless of whether the email exists (NFR-SEC-006)", async () => {
    mswServer.use(
      http.post("/api/v1/auth/password-reset/request", () => new HttpResponse(null, { status: 202 })),
    );

    const user = userEvent.setup();
    render(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email"), "maya@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(
      await screen.findByText(/we've sent a link to reset your password/i),
    ).toBeInTheDocument();
  });
});
