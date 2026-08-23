import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { DocumentsToolbar, type DocumentsFilters } from "./documents-toolbar";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const baseFilters: DocumentsFilters = {
  search: "",
  status: "all",
  tagId: "all",
  sort: "created_at_desc",
  view: "list",
};

describe("DocumentsToolbar — FR-DOC-002", () => {
  it("calls onChange with the typed search term", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DocumentsToolbar filters={baseFilters} onChange={onChange} onUpload={vi.fn()} />);

    await user.type(screen.getByRole("textbox", { name: "Search documents in this list" }), "x");

    expect(onChange).toHaveBeenCalledWith({ search: "x" });
  });

  it("reflects the active view in the toggle buttons' pressed state", () => {
    renderWithProviders(
      <DocumentsToolbar filters={{ ...baseFilters, view: "grid" }} onChange={vi.fn()} onUpload={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: "Grid view" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches the view on click", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DocumentsToolbar filters={baseFilters} onChange={onChange} onUpload={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Grid view" }));

    expect(onChange).toHaveBeenCalledWith({ view: "grid" });
  });

  it("calls onUpload when the Upload button is clicked", async () => {
    const onUpload = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DocumentsToolbar filters={baseFilters} onChange={vi.fn()} onUpload={onUpload} />);

    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(onUpload).toHaveBeenCalled();
  });
});
