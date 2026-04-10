import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import JobCard from "../JobCard";
import type { JobRecord } from "../../api/jobs";

const sampleJob: JobRecord = {
  id: "abc-123",
  user_id: "u1",
  status: "completed",
  config: {
    research_prompt: "AI tools for podcasters",
    num_ideas: 8,
    top_k: 3,
    score_threshold: 0.55,
    output_format: "markdown",
  },
  created_at: new Date("2026-04-10T12:00:00Z").toISOString(),
  started_at: null,
  completed_at: null,
  error: null,
  result: null,
};

describe("JobCard", () => {
  it("renders the prompt, status, and config summary", () => {
    render(
      <MemoryRouter>
        <JobCard job={sampleJob} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/AI tools for podcasters/)).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText(/8 ideas/)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/jobs/abc-123",
    );
  });
});
