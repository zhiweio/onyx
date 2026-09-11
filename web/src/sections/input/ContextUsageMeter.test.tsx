import { render, screen } from "@tests/setup/test-utils";
import ContextUsageMeter from "@/sections/input/ContextUsageMeter";

describe("ContextUsageMeter", () => {
  it("hides when the session has no used tokens", () => {
    const { container } = render(
      <ContextUsageMeter usedTokens={0} contextLimit={128_000} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("hides when the admin limit is missing", () => {
    const { container } = render(
      <ContextUsageMeter usedTokens={1_000} contextLimit={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the ring without a percent when usage is low", () => {
    render(<ContextUsageMeter usedTokens={10_000} contextLimit={128_000} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("10K / 128K · 8%");
    expect(screen.queryByText("8%")).not.toBeInTheDocument();
  });

  it("shows a percent at the warning threshold", () => {
    render(<ContextUsageMeter usedTokens={90_000} contextLimit={128_000} />);
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("shows a percent at the critical threshold", () => {
    render(<ContextUsageMeter usedTokens={120_000} contextLimit={128_000} />);
    expect(screen.getByText("94%")).toBeInTheDocument();
  });
});
