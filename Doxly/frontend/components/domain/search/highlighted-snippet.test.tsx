import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HighlightedSnippet } from "./highlighted-snippet";

describe("HighlightedSnippet — ui-ux.md §12, real <mark> semantics", () => {
  it("wraps only the matched range in a real <mark> element", () => {
    render(
      <HighlightedSnippet
        snippet={{ text: "Monthly rent is set at $1,800.", highlights: [{ start: 8, end: 12 }] }}
      />,
    );

    const mark = screen.getByText("rent");
    expect(mark.tagName).toBe("MARK");
  });

  it("renders plain text with no <mark> when there are no highlights", () => {
    render(<HighlightedSnippet snippet={{ text: "No matches here.", highlights: [] }} />);

    expect(screen.getByText("No matches here.")).toBeInTheDocument();
    expect(document.querySelector("mark")).not.toBeInTheDocument();
  });

  it("never interprets document text as markup — angle brackets render as literal text", () => {
    render(
      <HighlightedSnippet
        snippet={{ text: "Section <script>alert(1)</script> void.", highlights: [{ start: 8, end: 33 }] }}
      />,
    );

    expect(document.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
  });
});
