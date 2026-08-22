import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { mswServer } from "@/lib/test/msw-server";
import { VerifyEmailStatus } from "./verify-email-status";

describe("VerifyEmailStatus — FR-AUTH-002", () => {
  it("shows a missing-link message with no token, without calling the API", () => {
    render(<VerifyEmailStatus token={undefined} />);
    expect(
      screen.getByText("This verification link is missing or malformed."),
    ).toBeInTheDocument();
  });

  it("auto-verifies on mount and shows success", async () => {
    mswServer.use(
      http.post("/api/v1/auth/verify-email", () => HttpResponse.json({ verified: true })),
    );

    render(<VerifyEmailStatus token="valid-token" />);

    expect(
      await screen.findByText("Your email is verified. You're all set."),
    ).toBeInTheDocument();
  });

  it("shows an expired-link message on an invalid token", async () => {
    mswServer.use(
      http.post("/api/v1/auth/verify-email", () =>
        HttpResponse.json(
          { error: { code: "invalid_or_expired_token", message: "..." } },
          { status: 400 },
        ),
      ),
    );

    render(<VerifyEmailStatus token="expired-token" />);

    expect(
      await screen.findByText("This link has expired or is no longer valid."),
    ).toBeInTheDocument();
  });
});
