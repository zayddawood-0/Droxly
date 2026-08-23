import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PeriodSelector } from "./period-selector";

describe("PeriodSelector — ui-ux.md §13 (7d/30d/90d)", () => {
  it("marks the active period as pressed", () => {
    render(<PeriodSelector value="30d" onChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onChange with the selected period", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<PeriodSelector value="30d" onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "90 days" }));
    expect(onChange).toHaveBeenCalledWith("90d");
  });
});
