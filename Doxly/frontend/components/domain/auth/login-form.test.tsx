import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { mswServer } from "@/lib/test/msw-server";
import { LoginForm } from "./login-form";

const pushMock = vi.fn();
const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  refreshMock.mockClear();
});

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  render(<LoginForm />);
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
  return user;
}

describe("LoginForm — FR-AUTH-004", () => {
  it("blocks submission and shows a field error for an empty email", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText("Password"), "whatever");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Enter your email address")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("redirects to the dashboard on a successful login", async () => {
    mswServer.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({
          id: "u_1",
          email: "maya@example.com",
          display_name: "Maya",
          role: "user",
          plan: "free",
        }),
      ),
    );

    await fillAndSubmit("maya@example.com", "abcd1234");

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows one generic error for invalid credentials — never field-specific (NFR-SEC-006)", async () => {
    mswServer.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { error: { code: "invalid_credentials", message: "..." } },
          { status: 401 },
        ),
      ),
    );

    await fillAndSubmit("maya@example.com", "wrongpass");

    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("shows the dismissible connectivity banner on a 5xx/network failure, distinct from the credential error", async () => {
    mswServer.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { error: { code: "upstream_unavailable", message: "..." } },
          { status: 502 },
        ),
      ),
    );

    const user = await fillAndSubmit("maya@example.com", "abcd1234");

    const banner = await screen.findByText(
      "We couldn't reach Doxly. Check your connection and try again.",
    );
    expect(banner).toBeInTheDocument();
    expect(screen.queryByText("Invalid email or password.")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(
      screen.queryByText("We couldn't reach Doxly. Check your connection and try again."),
    ).not.toBeInTheDocument();
  });
});
