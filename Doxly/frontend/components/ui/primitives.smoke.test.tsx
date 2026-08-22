import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "./button";
import { Badge } from "./badge";
import { Card, CardContent, CardTitle } from "./card";
import { Input } from "./input";
import { Label } from "./label";
import { Skeleton } from "./skeleton";

/**
 * Foundation-tier smoke check (Phase 1 acceptance criteria): every installed
 * shadcn primitive renders without throwing. Deep behavioral coverage
 * (interaction, accessibility per component) lands alongside each primitive's
 * first real feature usage, not here.
 */
describe("shadcn primitives — render smoke", () => {
  it("Button", () => {
    render(<Button>Upload</Button>);
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });

  it("Badge", () => {
    render(<Badge>ready</Badge>);
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("Card", () => {
    render(
      <Card>
        <CardTitle>Invoice.pdf</CardTitle>
        <CardContent>2.4 MB</CardContent>
      </Card>,
    );
    expect(screen.getByText("Invoice.pdf")).toBeInTheDocument();
    expect(screen.getByText("2.4 MB")).toBeInTheDocument();
  });

  it("Input + Label", () => {
    render(
      <>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" />
      </>,
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("Skeleton", () => {
    const { container } = render(<Skeleton className="h-4 w-20" />);
    expect(container.firstChild).toBeInTheDocument();
  });
});
