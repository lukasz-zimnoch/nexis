import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusBadge from "../StatusBadge";

describe("StatusBadge", () => {
  it("renders the status text", () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByText("running");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("badge-running");
  });

  it("applies the correct class for completed", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText("completed")).toHaveClass("badge-completed");
  });
});
