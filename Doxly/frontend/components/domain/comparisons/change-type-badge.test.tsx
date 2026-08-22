import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChangeTypeBadge } from "./change-type-badge";

describe("ChangeTypeBadge — ui-ux.md §11", () => {
  it.each([
    ["addition", "Added"],
    ["deletion", "Removed"],
    ["modification", "Changed"],
    ["factual", "Factual"],
    ["numeric", "Numeric"],
    ["wording", "Wording"],
  ] as const)("renders a text label for %s, not color alone", (kind, label) => {
    render(<ChangeTypeBadge kind={kind} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
