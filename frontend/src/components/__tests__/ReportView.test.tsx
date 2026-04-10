import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ReportView from "../ReportView";

describe("ReportView", () => {
  it("renders an empty-state message when there are no reports", () => {
    render(<ReportView result={null} />);
    expect(screen.getByText(/no reports yet/i)).toBeInTheDocument();
  });

  it("renders markdown content from result items", () => {
    render(
      <ReportView
        result={[{ title: "Idea One", markdown: "## Heading\n\nbody text" }]}
      />,
    );
    expect(screen.getByText("Idea One")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByText("body text")).toBeInTheDocument();
  });
});
