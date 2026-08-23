import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnalyticsLineChart } from "./line-chart";

describe("AnalyticsLineChart — ui-ux.md §13", () => {
  it("renders without throwing and exposes the accessible data table", () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );

    render(
      <AnalyticsLineChart
        title="Documents processed over time"
        data={[
          { date: "2026-08-01", count: 3 },
          { date: "2026-08-02", count: 7 },
        ]}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01")).toBeInTheDocument();
  });
});
