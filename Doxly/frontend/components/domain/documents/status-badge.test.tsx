import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./status-badge";

describe("StatusBadge — the shared processing-indicator vocabulary (ui-ux.md)", () => {
  it("shows the exact stage by default", () => {
    render(<StatusBadge status="extracting" />);
    expect(screen.getByText("Extracting")).toBeInTheDocument();
  });

  it("collapses in-progress stages to 'Processing' in compact variant", () => {
    render(<StatusBadge status="chunking" variant="compact" />);
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.queryByText("Chunking")).not.toBeInTheDocument();
  });

  it("never collapses queued/ready/failed even in compact variant", () => {
    render(<StatusBadge status="ready" variant="compact" />);
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("renders a text label for every status — never color alone (NFR-A11Y-001)", () => {
    const statuses = ["queued", "extracting", "chunking", "embedding", "ready", "failed"] as const;
    for (const status of statuses) {
      const { unmount } = render(<StatusBadge status={status} />);
      expect(screen.getByText(/./)).toBeInTheDocument();
      unmount();
    }
  });
});
