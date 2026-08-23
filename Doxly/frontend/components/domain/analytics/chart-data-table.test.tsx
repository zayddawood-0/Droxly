import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartDataTable } from "./chart-data-table";

describe("ChartDataTable — ui-ux.md §13 accessible chart equivalent", () => {
  it("exposes every data point as real table rows", () => {
    render(
      <ChartDataTable
        caption="Documents processed over time"
        data={[
          { date: "2026-08-01", count: 3 },
          { date: "2026-08-02", count: 7 },
        ]}
      />,
    );

    expect(screen.getByText("Documents processed over time")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
    expect(screen.getByText("2026-08-01")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });
});
