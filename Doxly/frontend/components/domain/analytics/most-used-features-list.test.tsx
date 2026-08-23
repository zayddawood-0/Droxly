import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MostUsedFeaturesList } from "./most-used-features-list";

describe("MostUsedFeaturesList — ui-ux.md §13", () => {
  it("humanizes known feature keys and scales bar width to the max count", () => {
    render(
      <MostUsedFeaturesList
        features={[
          { feature: "chat", count: 40 },
          { feature: "extraction", count: 10 },
        ]}
      />,
    );

    expect(screen.getByText("AI Chat")).toBeInTheDocument();
    expect(screen.getByText("Extraction")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("title-cases an unrecognized feature key rather than showing a raw slug", () => {
    render(<MostUsedFeaturesList features={[{ feature: "custom_feature", count: 5 }]} />);
    expect(screen.getByText("Custom_feature")).toBeInTheDocument();
  });
});
