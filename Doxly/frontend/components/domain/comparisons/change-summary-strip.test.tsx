import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChangeSummaryStrip } from "./change-summary-strip";
import type { ComparisonResult } from "@/lib/api/comparisons";

const result: ComparisonResult = {
  alignment_quality: "high",
  message: null,
  additions: [{ document: "b", page_number: 1, excerpt: "new clause" }],
  deletions: [],
  modifications: [
    {
      change_type: "numeric",
      a_page_number: 2,
      a_excerpt: "$500",
      b_page_number: 2,
      b_excerpt: "$550",
      explanation: "Amount changed",
    },
  ],
};

describe("ChangeSummaryStrip — FR-COMP-002 counts by type", () => {
  it("shows a count per change category", () => {
    render(<ChangeSummaryStrip result={result} filter={null} onFilterChange={vi.fn()} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    expect(buttons.find((b) => /Added/.test(b.textContent ?? ""))?.textContent).toContain("1");
    expect(buttons.find((b) => /Removed/.test(b.textContent ?? ""))?.textContent).toContain("0");
    expect(buttons.find((b) => /Changed/.test(b.textContent ?? ""))?.textContent).toContain("1");
  });

  it("toggles a filter on click, and clears it on a second click", async () => {
    const onFilterChange = vi.fn();
    const user = userEvent.setup();
    render(<ChangeSummaryStrip result={result} filter={null} onFilterChange={onFilterChange} />);

    await user.click(screen.getByRole("button", { name: /Added/ }));
    expect(onFilterChange).toHaveBeenCalledWith("addition");
  });

  it("clears the active filter when its chip is clicked again", async () => {
    const onFilterChange = vi.fn();
    const user = userEvent.setup();
    render(<ChangeSummaryStrip result={result} filter="addition" onFilterChange={onFilterChange} />);

    await user.click(screen.getByRole("button", { name: /Added/ }));
    expect(onFilterChange).toHaveBeenCalledWith(null);
  });
});
