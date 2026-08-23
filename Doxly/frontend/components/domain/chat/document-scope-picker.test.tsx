import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { DocumentScopePicker } from "./document-scope-picker";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const documents = {
  items: [
    { id: "doc_1", file_name: "lease.pdf" },
    { id: "doc_2", file_name: "invoice.pdf" },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

describe("DocumentScopePicker — FR-AI-002", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("labels an empty selection as workspace-wide", () => {
    renderWithProviders(<DocumentScopePicker selectedIds={[]} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /All documents/ })).toBeInTheDocument();
  });

  it("labels a single selection with the document's file name", () => {
    mswServer.use(http.get("/api/v1/documents", () => HttpResponse.json(documents)));
    renderWithProviders(<DocumentScopePicker selectedIds={["doc_1"]} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /1 document/ })).toBeInTheDocument();
  });

  it("labels multiple selections with a count", () => {
    renderWithProviders(<DocumentScopePicker selectedIds={["doc_1", "doc_2"]} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /2 documents/ })).toBeInTheDocument();
  });

  it("toggles a document into the selection on select", async () => {
    mswServer.use(http.get("/api/v1/documents", () => HttpResponse.json(documents)));
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DocumentScopePicker selectedIds={[]} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /All documents/ }));
    await user.click(await screen.findByText("lease.pdf"));

    expect(onChange).toHaveBeenCalledWith(["doc_1"]);
  });

  it("is disabled while streaming", () => {
    renderWithProviders(<DocumentScopePicker selectedIds={[]} onChange={vi.fn()} disabled />);
    expect(screen.getByRole("button", { name: /All documents/ })).toBeDisabled();
  });
});
