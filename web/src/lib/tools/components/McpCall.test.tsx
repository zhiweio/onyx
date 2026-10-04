import React from "react";
import { fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import {
  McpCallDetails,
  McpResultBlock,
  McpSummaryLine,
} from "@/lib/tools/components/McpCall";

describe("McpSummaryLine", () => {
  it("renders MCP label, server name, separator, and tool name", () => {
    render(
      <McpSummaryLine
        serverName="Cognitational/deepwiki"
        toolName="Ask wiki question"
        running={false}
      />,
    );
    expect(screen.getByText("MCP")).toBeInTheDocument();
    expect(screen.getByText("Cognitational/deepwiki")).toBeInTheDocument();
    expect(screen.getByText("·")).toBeInTheDocument();
    expect(screen.getByText("Ask wiki question")).toBeInTheDocument();
  });

  it("omits the server name when unknown", () => {
    render(<McpSummaryLine toolName="rag_search" />);
    expect(screen.getByText("MCP")).toBeInTheDocument();
    expect(screen.getByText("rag_search")).toBeInTheDocument();
  });
});

describe("McpResultBlock", () => {
  it("renders compact single-line results without a code block", () => {
    render(<McpResultBlock result="Done, 3 files updated" />);
    expect(screen.getByText("Done, 3 files updated")).toBeInTheDocument();
    expect(screen.queryByText("Result")).not.toBeInTheDocument();
  });

  it("renders long results in a Result block with copy", () => {
    const long = "x".repeat(200);
    render(<McpResultBlock result={long} />);
    expect(screen.getByText("Result")).toBeInTheDocument();
  });
});

describe("McpCallDetails", () => {
  it("expands to Description and Parameters", () => {
    render(
      <McpCallDetails
        description="Ask any question about a repo"
        parameters={{ repoName: "vercel/next.js" }}
      />,
    );
    fireEvent.click(screen.getByText("View call details"));

    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(
      screen.getByText("Ask any question about a repo"),
    ).toBeInTheDocument();
    expect(screen.getByText("Parameters")).toBeInTheDocument();
    expect(screen.getByText(/vercel\/next\.js/)).toBeInTheDocument();
  });

  it("stays collapsed until clicked", () => {
    render(<McpCallDetails parameters={{ a: 1 }} />);
    // Radix keeps the collapsed content unmounted.
    expect(screen.queryByText("Parameters")).toBeNull();
  });
});
