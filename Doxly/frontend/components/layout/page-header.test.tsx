import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "./page-header";

describe("PageHeader", () => {
  it("renders the title as a heading", () => {
    render(<PageHeader title="Documents" />);
    expect(
      screen.getByRole("heading", { name: "Documents" }),
    ).toBeInTheDocument();
  });

  it("renders the description when provided", () => {
    render(<PageHeader title="Documents" description="All your files." />);
    expect(screen.getByText("All your files.")).toBeInTheDocument();
  });

  it("omits the description paragraph when none is provided", () => {
    render(<PageHeader title="Documents" />);
    expect(screen.queryByText("All your files.")).not.toBeInTheDocument();
  });

  it("renders provided actions", () => {
    render(<PageHeader title="Documents" actions={<button>Upload</button>} />);
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });
});
