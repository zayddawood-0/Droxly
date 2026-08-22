import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DiffView } from "./diff-view";
import type { ComparisonResult } from "@/lib/api/comparisons";

const result: ComparisonResult = {
  alignment_quality: "high",
  message: null,
  additions: [{ document: "b", page_number: 3, excerpt: "New indemnification clause." }],
  deletions: [{ document: "a", page_number: 1, excerpt: "Obsolete termination clause." }],
  modifications: [
    {
      change_type: "numeric",
      a_page_number: 2,
      a_excerpt: "$500",
      b_page_number: 2,
      b_excerpt: "$550",
      explanation: "Total amount changed",
    },
  ],
};

describe("DiffView — FR-COMP-001/002", () => {
  it("renders every addition, deletion, and modification excerpt", () => {
    render(<DiffView result={result} documentAId="doc_a" documentBId="doc_b" filter={null} />);

    // Desktop grid + mobile stack both render simultaneously in jsdom.
    expect(screen.getAllByText(/New indemnification clause/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Obsolete termination clause/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\$500/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\$550/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Total amount changed").length).toBeGreaterThan(0);
  });

  it("filters down to only the selected change type", () => {
    render(<DiffView result={result} documentAId="doc_a" documentBId="doc_b" filter="addition" />);

    expect(screen.getAllByText(/New indemnification clause/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Obsolete termination clause/)).not.toBeInTheDocument();
    expect(screen.queryByText("Total amount changed")).not.toBeInTheDocument();
  });

  it("shows an explanatory empty state when there are no differences at all", () => {
    const empty: ComparisonResult = {
      alignment_quality: "high",
      message: null,
      additions: [],
      deletions: [],
      modifications: [],
    };
    render(<DiffView result={empty} documentAId="doc_a" documentBId="doc_b" filter={null} />);

    expect(screen.getByText("No differences found between these documents.")).toBeInTheDocument();
  });

  it("shows a distinct message when a filter matches nothing", () => {
    render(<DiffView result={result} documentAId="doc_a" documentBId="doc_b" filter="deletion" />);
    // Switch to a filter with zero matches by reusing modifications-only data.
    const modsOnly: ComparisonResult = { ...result, additions: [], deletions: [] };
    render(<DiffView result={modsOnly} documentAId="doc_a" documentBId="doc_b" filter="addition" />);

    expect(screen.getByText("No changes match this filter.")).toBeInTheDocument();
  });
});
