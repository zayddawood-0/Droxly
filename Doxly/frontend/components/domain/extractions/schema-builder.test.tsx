import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SchemaBuilder } from "./schema-builder";
import type { SchemaField } from "@/lib/api/extractions";

describe("SchemaBuilder — FR-EXT-001 custom schema", () => {
  it("updates a field's name as the user types", async () => {
    // SchemaBuilder is a controlled component (fields come from props) —
    // typing a single character is the correct way to test it without a
    // parent re-render loop feeding each keystroke back in.
    const fields: SchemaField[] = [{ name: "total", type: "string", required: false }];
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SchemaBuilder fields={fields} onChange={onChange} />);

    await user.type(screen.getByLabelText("Field 1 name"), "!");

    expect(onChange).toHaveBeenCalledWith([{ name: "total!", type: "string", required: false }]);
  });

  it("toggles the required checkbox", async () => {
    const fields: SchemaField[] = [{ name: "total", type: "number", required: false }];
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SchemaBuilder fields={fields} onChange={onChange} />);

    await user.click(screen.getByLabelText("Field 1 required"));

    expect(onChange).toHaveBeenCalledWith([{ name: "total", type: "number", required: true }]);
  });

  it("adds a new blank row", async () => {
    const fields: SchemaField[] = [{ name: "a", type: "string", required: false }];
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SchemaBuilder fields={fields} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Add field" }));

    expect(onChange).toHaveBeenCalledWith([
      { name: "a", type: "string", required: false },
      { name: "", type: "string", required: false },
    ]);
  });

  it("removes a row, but never the last remaining one", async () => {
    const twoFields: SchemaField[] = [
      { name: "a", type: "string", required: false },
      { name: "b", type: "string", required: false },
    ];
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<SchemaBuilder fields={twoFields} onChange={onChange} />);

    await user.click(screen.getByLabelText("Remove field 1"));
    expect(onChange).toHaveBeenCalledWith([{ name: "b", type: "string", required: false }]);

    rerender(
      <SchemaBuilder fields={[{ name: "b", type: "string", required: false }]} onChange={onChange} />,
    );
    expect(screen.getByLabelText("Remove field 1")).toBeDisabled();
  });
});
