import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfidenceBadge } from "./confidence-badge";

describe("ConfidenceBadge — ui-ux.md §10 (text/icon in addition to color, NFR-A11Y-001)", () => {
  it("shows a percentage, never color alone", () => {
    render(<ConfidenceBadge confidence={0.92} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("shows a dash for a null confidence", () => {
    render(<ConfidenceBadge confidence={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("uses distinct styling across high/medium/low buckets", () => {
    const { container: high } = render(<ConfidenceBadge confidence={0.95} />);
    const { container: medium } = render(<ConfidenceBadge confidence={0.6} />);
    const { container: low } = render(<ConfidenceBadge confidence={0.2} />);

    expect(high.textContent).toBe("95%");
    expect(medium.textContent).toBe("60%");
    expect(low.textContent).toBe("20%");
    expect(high.querySelector(".text-success")).toBeInTheDocument();
    expect(medium.querySelector(".text-info")).toBeInTheDocument();
    expect(low.querySelector(".text-danger")).toBeInTheDocument();
  });
});
