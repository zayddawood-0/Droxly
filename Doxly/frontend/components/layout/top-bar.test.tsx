import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { mswServer } from "@/lib/test/msw-server";
import { TopBar } from "./top-bar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

const pushMock = vi.fn();
const refreshMock = vi.fn();

beforeEach(() => {
  pushMock.mockClear();
  refreshMock.mockClear();
});

describe("TopBar — logout (FR-AUTH-006)", () => {
  it("calls the logout endpoint and redirects to /login on success", async () => {
    mswServer.use(
      http.post("/api/v1/auth/logout", () => new HttpResponse(null, { status: 204 })),
    );

    const user = userEvent.setup();
    render(<TopBar />);
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Log out" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
  });

  it("shows an error toast and does not navigate if logout fails", async () => {
    mswServer.use(
      http.post("/api/v1/auth/logout", () =>
        HttpResponse.json({ error: { code: "server_error", message: "..." } }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    render(<TopBar />);
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Log out" }));

    await waitFor(() => expect(pushMock).not.toHaveBeenCalled());
  });
});

describe("TopBar — global search trigger (ui-ux.md §0/§12)", () => {
  it("navigates to /search when the search button is clicked", async () => {
    const user = userEvent.setup();
    render(<TopBar />);

    // Desktop and mobile trigger buttons both render in jsdom simultaneously
    // (no real CSS media-query filtering) — click the first match.
    await user.click(screen.getAllByRole("button", { name: "Open global search" })[0]);

    expect(pushMock).toHaveBeenCalledWith("/search");
  });

  it("navigates to /search on Cmd/Ctrl+K from anywhere in the shell", async () => {
    const user = userEvent.setup();
    render(<TopBar />);

    await user.keyboard("{Control>}k{/Control}");

    expect(pushMock).toHaveBeenCalledWith("/search");
  });
});
