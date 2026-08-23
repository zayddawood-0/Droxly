import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResultCard, groupResultsByDocument } from "./result-card";
import type { SearchResultRow } from "@/lib/api/search";

const rows: SearchResultRow[] = [
  {
    document_id: "doc_1",
    file_name: "lease.pdf",
    snippet: { text: "Monthly rent is $1,800.", highlights: [{ start: 17, end: 23 }] },
    relevance_score: 0.9,
    matched_page: 1,
  },
  {
    document_id: "doc_1",
    file_name: "lease.pdf",
    snippet: { text: "Tenant shall maintain insurance.", highlights: [{ start: 22, end: 31 }] },
    relevance_score: 0.7,
    matched_page: 4,
  },
  {
    document_id: "doc_2",
    file_name: "invoice.pdf",
    snippet: { text: "Total due: $500.", highlights: [{ start: 11, end: 15 }] },
    relevance_score: 0.8,
    matched_page: null,
  },
];

describe("groupResultsByDocument — api.md §8 (one row per matching chunk)", () => {
  it("groups rows sharing a document_id into a single result", () => {
    const grouped = groupResultsByDocument(rows);

    expect(grouped).toHaveLength(2);
    expect(grouped[0].document_id).toBe("doc_1");
    expect(grouped[0].matches).toHaveLength(2);
    expect(grouped[1].document_id).toBe("doc_2");
    expect(grouped[1].matches).toHaveLength(1);
  });
});

describe("ResultCard — ui-ux.md §12", () => {
  it("renders every snippet for the document and links each to its matched page", () => {
    const grouped = groupResultsByDocument(rows);
    render(<ResultCard result={grouped[0]} />);

    expect(screen.getByText("lease.pdf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Monthly rent is \$1,800\./ })).toHaveAttribute(
      "href",
      "/documents/doc_1?page=1",
    );
    expect(screen.getByRole("link", { name: /Tenant shall maintain insurance\./ })).toHaveAttribute(
      "href",
      "/documents/doc_1?page=4",
    );
  });

  it("omits the ?page= query param when a match has no matched page", () => {
    const grouped = groupResultsByDocument(rows);
    render(<ResultCard result={grouped[1]} />);

    expect(screen.getByRole("link", { name: /Total due: \$500\./ })).toHaveAttribute(
      "href",
      "/documents/doc_2",
    );
  });
});
