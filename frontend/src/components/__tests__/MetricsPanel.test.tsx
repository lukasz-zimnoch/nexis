import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import MetricsPanel from "../MetricsPanel";
import type { CallMetrics, RunMetrics } from "../../api/jobs";

function bucket(overrides: Partial<CallMetrics> = {}): CallMetrics {
  return {
    calls: 1,
    input_tokens: 1_000,
    output_tokens: 200,
    cost_usd: 0.01,
    llm_seconds: 1.5,
    ...overrides,
  };
}

const sampleMetrics: RunMetrics = {
  run_id: "job-abc",
  wall_seconds: 92.5,
  totals: bucket({ calls: 3, input_tokens: 3_000, output_tokens: 600, cost_usd: 0.03 }),
  by_layer: {
    research: bucket(),
    review: bucket({ calls: 2, cost_usd: 0.02 }),
  },
  by_agent: { ResearchAgent: bucket() },
  prompt_versions: { ResearchAgent: "abc123abc123" },
  unpriced_models: [],
};

describe("MetricsPanel", () => {
  it("reports an empty state when the job has no metrics", () => {
    render(<MetricsPanel metrics={null} />);
    expect(screen.getByText(/no run metrics recorded/i)).toBeInTheDocument();
  });

  it("shows the run totals", () => {
    render(<MetricsPanel metrics={sampleMetrics} />);
    expect(screen.getByText("$0.0300")).toBeInTheDocument();
    expect(screen.getByText("3,600")).toBeInTheDocument();
    expect(screen.getByText("1 m 33 s")).toBeInTheDocument();
  });

  it("breaks the totals down per layer", () => {
    render(<MetricsPanel metrics={sampleMetrics} />);
    expect(screen.getByText("research")).toBeInTheDocument();
    expect(screen.getByText("review")).toBeInTheDocument();
    expect(screen.getByText("$0.0200")).toBeInTheDocument();
  });

  it("lists the prompt version of each agent", () => {
    render(<MetricsPanel metrics={sampleMetrics} />);
    expect(screen.getByText("abc123abc123")).toBeInTheDocument();
  });

  it("warns that a model without a price is missing from the cost", () => {
    render(
      <MetricsPanel
        metrics={{ ...sampleMetrics, unpriced_models: ["acme/unreleased-model"] }}
      />,
    );
    expect(screen.getByText(/acme\/unreleased-model/)).toBeInTheDocument();
    expect(screen.getByText(/cost excludes/i)).toBeInTheDocument();
  });
});
