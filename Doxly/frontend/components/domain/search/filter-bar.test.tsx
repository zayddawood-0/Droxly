import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { FilterBar, EMPTY_SEARCH_FILTERS, countActiveFilters, type SearchFilters } from "./filter-bar";

function renderWithProviders(ui: React.ReactElement) {
  mswServer.use(http.get("/api/v1/tags", () => HttpResponse.json({ items: [] })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("countActiveFilters — Search filter chip count", () => {
  it("counts 0 for the empty filter set", () => {
    expect(countActiveFilters(EMPTY_SEARCH_FILTERS)).toBe(0);
  });

  it("counts each non-default field once", () => {
    const filters: SearchFilters = {
      mimeType: "application/pdf",
      tagId: "tag_1",
      status: "ready",
      dateFrom: "2026-01-01",
      dateTo: "2026-02-01",
    };
    expect(countActiveFilters(filters)).toBe(5);
  });
});

describe("FilterBar — ui-ux.md §12 filter row / mobile sheet", () => {
  it("only shows 'Clear filters' once a filter is active", () => {
    const { rerender } = renderWithProviders(
      <FilterBar filters={EMPTY_SEARCH_FILTERS} onChange={vi.fn()} />,
    );
    expect(screen.queryAllByRole("button", { name: "Clear filters" })).toHaveLength(0);

    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <FilterBar filters={{ ...EMPTY_SEARCH_FILTERS, tagId: "tag_1" }} onChange={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getAllByRole("button", { name: "Clear filters" }).length).toBeGreaterThan(0);
  });

  it("resets every field when 'Clear filters' is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <FilterBar filters={{ ...EMPTY_SEARCH_FILTERS, mimeType: "application/pdf" }} onChange={onChange} />,
    );

    await user.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(onChange).toHaveBeenCalledWith(EMPTY_SEARCH_FILTERS);
  });

  it("shows an active-filter count badge on the mobile Filters trigger", () => {
    renderWithProviders(
      <FilterBar filters={{ ...EMPTY_SEARCH_FILTERS, status: "ready" }} onChange={vi.fn()} />,
    );

    const trigger = screen.getByRole("button", { name: /Filters/ });
    expect(trigger.textContent).toContain("1");
  });
});
