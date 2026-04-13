import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ReportView from "../ReportView";
import type { Report } from "../../api/jobs";

const sampleReport: Report = {
  title: "Idea One",
  generated_at: "2026-04-10T12:00:00Z",
  ideas_evaluated: 8,
  ideas_selected: 3,
  content: "## Heading\n\nbody text",
  format: "markdown",
};

describe("ReportView", () => {
  it("renders an empty-state message when there are no reports", () => {
    render(<ReportView result={null} />);
    expect(screen.getByText(/no reports yet/i)).toBeInTheDocument();
  });

  it("renders markdown content from a report", () => {
    render(<ReportView result={[sampleReport]} />);
    expect(screen.getByText("Idea One")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByText("body text")).toBeInTheDocument();
  });

  it("renders json content as a preformatted block", () => {
    render(
      <ReportView
        result={[{ ...sampleReport, format: "json", content: '{"foo":1}' }]}
      />,
    );
    expect(screen.getByText('{"foo":1}')).toBeInTheDocument();
  });
});
