import { render, screen } from "@testing-library/react";
import { FileText } from "lucide-react";
import { describe, expect, it } from "vitest";

import { StatCard, StatCardSkeleton } from "./stat-card";

describe("StatCard — ui-ux.md §13", () => {
  it("renders the label and value", () => {
    render(<StatCard icon={FileText} label="Documents processed" value="42" />);

    expect(screen.getByText("Documents processed")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("StatCardSkeleton renders a loading placeholder with no data text", () => {
    render(<StatCardSkeleton />);
    expect(screen.queryByText("Documents processed")).not.toBeInTheDocument();
  });
});
