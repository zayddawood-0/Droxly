import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { AdminGuard } from "./admin-guard";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const baseUser = {
  id: "user_1",
  email: "a@example.com",
  display_name: "A",
  avatar_url: null,
  plan: "free",
  email_verified: true,
  storage_used_bytes: 0,
  created_at: "2026-01-01T00:00:00Z",
};

describe("AdminGuard — security.md §3.1 role check for /admin/*", () => {
  it("renders the admin shell and children once role === admin is confirmed", async () => {
    mswServer.use(
      http.get("/api/v1/users/me", () => HttpResponse.json({ ...baseUser, role: "admin" })),
    );

    renderWithProviders(
      <AdminGuard>
        <p>Admin content</p>
      </AdminGuard>,
    );

    expect(await screen.findByText("Admin content")).toBeInTheDocument();
    expect(screen.getByText("Doxly — Internal Admin")).toBeInTheDocument();
  });

  it("shows a permission-denied state, never the admin shell, for a non-admin user", async () => {
    mswServer.use(
      http.get("/api/v1/users/me", () => HttpResponse.json({ ...baseUser, role: "user" })),
    );

    renderWithProviders(
      <AdminGuard>
        <p>Admin content</p>
      </AdminGuard>,
    );

    expect(
      await screen.findByText("You don't have permission to view this page."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Admin content")).not.toBeInTheDocument();
    expect(screen.queryByText("Doxly — Internal Admin")).not.toBeInTheDocument();
  });

  it("fails closed — never shows admin content when role can't be verified", async () => {
    mswServer.use(
      http.get("/api/v1/users/me", () =>
        HttpResponse.json({ error: { code: "server_error", message: "..." } }, { status: 500 }),
      ),
    );

    renderWithProviders(
      <AdminGuard>
        <p>Admin content</p>
      </AdminGuard>,
    );

    expect(
      await screen.findByText("We couldn't verify admin access right now."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Admin content")).not.toBeInTheDocument();
  });
});
