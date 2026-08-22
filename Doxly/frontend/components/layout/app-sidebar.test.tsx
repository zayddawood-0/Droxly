import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppSidebar } from "./app-sidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/documents",
}));

describe("AppSidebar", () => {
  it("renders every primary nav item from specs/ui-ux.md §0", () => {
    render(<AppSidebar />);
    for (const label of [
      "Dashboard",
      "Documents",
      "AI Chat",
      "Extractions",
      "Compare",
      "Search",
      "Analytics",
      "Settings",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("marks the current route as the active page", () => {
    render(<AppSidebar />);
    const documentsLink = screen.getByRole("link", { name: "Documents" });
    expect(documentsLink).toHaveAttribute("aria-current", "page");

    const dashboardLink = screen.getByRole("link", { name: "Dashboard" });
    expect(dashboardLink).not.toHaveAttribute("aria-current");
  });

  it("links Documents to /documents", () => {
    render(<AppSidebar />);
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute(
      "href",
      "/documents",
    );
  });
});
