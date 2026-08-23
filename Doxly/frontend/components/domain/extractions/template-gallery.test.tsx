import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { mswServer } from "@/lib/test/msw-server";
import { TemplateGallery } from "./template-gallery";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const templates = {
  items: [
    { key: "invoice", name: "Invoice", description: "Vendor, total, due date", fields: [{ name: "vendor", type: "string", description: "", required: true }] },
    { key: "contract", name: "Contract", description: "Parties, term", fields: [] },
  ],
};

describe("TemplateGallery — FR-EXT-002", () => {
  it("shows a connectivity error with retry, not a blank gallery", async () => {
    mswServer.use(
      http.get("/api/v1/extractions/templates", () =>
        HttpResponse.json({ error: { code: "server_error", message: "..." } }, { status: 500 }),
      ),
    );

    renderWithProviders(<TemplateGallery selectedKey={null} onSelect={vi.fn()} onSelectCustom={vi.fn()} />);

    expect(await screen.findByText("Couldn't load extraction templates.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders every template plus the custom-schema card, and calls onSelect with the chosen key", async () => {
    mswServer.use(http.get("/api/v1/extractions/templates", () => HttpResponse.json(templates)));
    const onSelect = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(<TemplateGallery selectedKey={null} onSelect={onSelect} onSelectCustom={vi.fn()} />);

    expect(await screen.findByText("Invoice")).toBeInTheDocument();
    expect(screen.getByText("Contract")).toBeInTheDocument();
    expect(screen.getByText("Custom schema")).toBeInTheDocument();
    expect(screen.getByText("1 field")).toBeInTheDocument();
    expect(screen.getByText("0 fields")).toBeInTheDocument();

    await user.click(screen.getByText("Invoice"));
    expect(onSelect).toHaveBeenCalledWith("invoice");
  });

  it("calls onSelectCustom when the custom-schema card is clicked", async () => {
    mswServer.use(http.get("/api/v1/extractions/templates", () => HttpResponse.json(templates)));
    const onSelectCustom = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(<TemplateGallery selectedKey={null} onSelect={vi.fn()} onSelectCustom={onSelectCustom} />);

    await user.click(await screen.findByText("Custom schema"));
    expect(onSelectCustom).toHaveBeenCalled();
  });
});
