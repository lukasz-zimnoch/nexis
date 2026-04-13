import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JobForm from "../JobForm";

describe("JobForm", () => {
  it("disables the submit button until a research prompt is entered", async () => {
    const onSubmit = vi.fn();
    render(<JobForm onSubmit={onSubmit} />);

    const button = screen.getByRole("button", { name: /run pipeline/i });
    expect(button).toBeDisabled();

    await userEvent.type(
      screen.getByLabelText(/research prompt/i),
      "AI tools for podcasters",
    );
    expect(button).toBeEnabled();
  });

  it("submits the configured values", async () => {
    const onSubmit = vi.fn();
    render(<JobForm onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByLabelText(/research prompt/i),
      "topic",
    );
    await userEvent.click(screen.getByRole("button", { name: /run pipeline/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        research_prompt: "topic",
        num_ideas: 8,
        top_k: 3,
        score_threshold: 0.55,
        output_format: "markdown",
      }),
    );
  });
});
