import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Table, TableBody } from "@/components/ui/table";
import { ExtractionFieldRow } from "./extraction-field-row";
import type { ExtractionResultField } from "@/lib/api/extractions";

function renderRow(field: ExtractionResultField, onSave = vi.fn().mockResolvedValue(undefined)) {
  render(
    <Table>
      <TableBody>
        <ExtractionFieldRow field={field} onSave={onSave} />
      </TableBody>
    </Table>,
  );
  return onSave;
}

describe("ExtractionFieldRow — FR-EXT-003, FR-EXT-004", () => {
  it("shows a not-found value in a distinct muted state with the reason, never blank", () => {
    renderRow({
      field: "due_date",
      value: null,
      confidence: null,
      not_found_reason: "not mentioned in the document",
      corrected: false,
      citation: null,
    });

    expect(screen.getByText("Not found in document")).toBeInTheDocument();
  });

  it("renders the citation source when present", () => {
    renderRow({
      field: "total",
      value: "500",
      confidence: 0.9,
      not_found_reason: null,
      corrected: false,
      citation: { page_number: 2, snippet: "Total due: $500" },
    });

    expect(screen.getByText(/p\. 2 — Total due: \$500/)).toBeInTheDocument();
  });

  it("saves an edit on Enter and cancels on Escape", async () => {
    const onSave = renderRow({
      field: "vendor_name",
      value: "Acme Corp",
      confidence: 0.8,
      not_found_reason: null,
      corrected: false,
      citation: null,
    });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit vendor_name" }));
    const input = screen.getByLabelText("Edit value for vendor_name");
    await user.clear(input);
    await user.type(input, "Acme Corporation{Enter}");

    expect(onSave).toHaveBeenCalledWith("Acme Corporation");
  });

  it("cancels an in-progress edit on Escape without saving", async () => {
    const onSave = renderRow({
      field: "vendor_name",
      value: "Acme Corp",
      confidence: 0.8,
      not_found_reason: null,
      corrected: false,
      citation: null,
    });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit vendor_name" }));
    await user.type(screen.getByLabelText("Edit value for vendor_name"), "{Escape}");

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
  });

  it("shows a corrected value with distinct styling", () => {
    renderRow({
      field: "total",
      value: "550",
      confidence: 0.9,
      not_found_reason: null,
      corrected: true,
      citation: null,
    });

    expect(screen.getByText("550").className).toContain("text-primary");
  });
});
