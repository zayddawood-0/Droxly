import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PhasePlaceholder } from "./phase-placeholder";

describe("PhasePlaceholder", () => {
  it("names the owning phase", () => {
    render(<PhasePlaceholder phase="Phase 9 — AI Chat" />);
    expect(screen.getByText("Phase 9 — AI Chat")).toBeInTheDocument();
  });

  it("renders requirement IDs when provided", () => {
    render(
      <PhasePlaceholder phase="Phase 9 — AI Chat" requirements="FR-AI-001" />,
    );
    expect(screen.getByText("FR-AI-001")).toBeInTheDocument();
  });
});
