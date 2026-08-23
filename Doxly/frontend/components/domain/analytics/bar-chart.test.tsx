import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnalyticsBarChart } from "./bar-chart";

describe("AnalyticsBarChart — ui-ux.md §13", () => {
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
      <AnalyticsBarChart
        title="AI requests over time"
        data={[
          { date: "2026-08-01", count: 2 },
          { date: "2026-08-02", count: 5 },
        ]}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("2026-08-02")).toBeInTheDocument();
  });
});
