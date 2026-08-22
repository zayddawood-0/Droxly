import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { DocumentPicker } from "./document-picker";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DocumentPicker — Comparison's Document A/B pair (ui-ux.md §11)", () => {
  beforeEach(() => {
    // cmdk's Command list measures/scrolls items via APIs jsdom doesn't implement.
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

  it("excludes the document already selected in the paired picker", async () => {
    mswServer.use(
      http.get("/api/v1/documents", () =>
        HttpResponse.json({
          items: [
            { id: "doc_1", file_name: "contract-v1.pdf" },
            { id: "doc_2", file_name: "contract-v2.pdf" },
          ],
          total: 2,
          limit: 100,
          offset: 0,
        }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<DocumentPicker selectedId={null} onChange={vi.fn()} excludeId="doc_1" />);

    await user.click(screen.getByRole("button", { name: /select a document/i }));

    expect(await screen.findByText("contract-v2.pdf")).toBeInTheDocument();
    expect(screen.queryByText("contract-v1.pdf")).not.toBeInTheDocument();
  });
});
