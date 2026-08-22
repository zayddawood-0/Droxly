import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { mswServer } from "@/lib/test/msw-server";
import { RegisterForm } from "./register-form";

const pushMock = vi.fn();
const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  refreshMock.mockClear();
});

async function fillForm(name: string, email: string, password: string) {
  const user = userEvent.setup();
  render(<RegisterForm />);
  await user.type(screen.getByLabelText("Name"), name);
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  return user;
}

describe("RegisterForm — FR-AUTH-001", () => {
  it("shows live password-policy feedback as the user types", async () => {
    const user = userEvent.setup();
    render(<RegisterForm />);
    await user.type(screen.getByLabelText("Password"), "abc");

    expect(screen.getByText("At least one number")).toBeInTheDocument();
    // The strength meter's own criteria list, not the field-level error —
    // submit hasn't happened yet, so no FieldError is rendered.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("redirects to the dashboard on successful registration", async () => {
    mswServer.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { id: "u_1", email: "maya@example.com", display_name: "Maya", email_verified: false },
          { status: 201 },
        ),
      ),
    );

    const user = await fillForm("Maya", "maya@example.com", "abcd1234");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows one generic message for a duplicate email — never 'email already registered' (NFR-SEC-006)", async () => {
    mswServer.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { error: { code: "registration_failed", message: "..." } },
          { status: 400 },
        ),
      ),
    );

    const user = await fillForm("Maya", "maya@example.com", "abcd1234");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText(
        "We couldn't create your account. Check your details and try again.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/already registered/i)).not.toBeInTheDocument();
  });

  it("maps a 422 field error from the server onto the matching form field", async () => {
    mswServer.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            error: {
              code: "validation_error",
              message: "...",
              fields: { email: "This email format isn't valid." },
            },
          },
          { status: 422 },
        ),
      ),
    );

    const user = await fillForm("Maya", "maya@example.com", "abcd1234");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText("This email format isn't valid."),
    ).toBeInTheDocument();
  });
});
