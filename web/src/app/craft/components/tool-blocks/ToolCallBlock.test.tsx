import { fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import ToolCallBlock from "@/app/craft/components/tool-blocks/ToolCallBlock";
import { ToolGroupRow } from "@/app/craft/components/tool-blocks/ToolGroupRow";
import {
  getToolLayoutOpen,
  setToolLayoutOpen,
  toolLayoutOpenState,
} from "@/app/craft/components/tool-blocks/toolLayoutStore";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

function bashTool(overrides: Partial<ToolCallState> = {}): ToolCallState {
  return {
    id: "tool-1",
    kind: "execute",
    title: "Bash",
    description: "Running tests",
    command: "bun test",
    status: "completed",
    rawOutput: "3 passed",
    ...overrides,
  };
}

function editTool(overrides: Partial<ToolCallState> = {}): ToolCallState {
  return {
    id: "tool-edit",
    kind: "edit",
    title: "Edit",
    description: "src/app/page.tsx",
    command: "",
    status: "completed",
    rawOutput: "",
    oldContent: "a\nb\nx\nc",
    newContent: "a\nb\nc\nd\ne",
    ...overrides,
  };
}

describe("toolLayoutStore", () => {
  beforeEach(() => {
    toolLayoutOpenState.clear();
  });

  it("round-trips open state by tool id", () => {
    expect(getToolLayoutOpen("t1")).toBeUndefined();
    setToolLayoutOpen("t1", true);
    expect(getToolLayoutOpen("t1")).toBe(true);
  });

  it("evicts the oldest entry once the cap is exceeded", () => {
    for (let i = 0; i < 2000; i += 1) {
      setToolLayoutOpen(`t-${i}`, true);
    }
    // At the cap nothing has been evicted yet.
    expect(getToolLayoutOpen("t-0")).toBe(true);
    setToolLayoutOpen("t-new", true);
    expect(getToolLayoutOpen("t-0")).toBeUndefined();
    expect(getToolLayoutOpen("t-1")).toBe(true);
    expect(getToolLayoutOpen("t-new")).toBe(true);
  });
});

describe("ToolCallBlock", () => {
  beforeEach(() => {
    toolLayoutOpenState.clear();
  });

  it("renders the tool summary with kind label and status", () => {
    render(<ToolCallBlock toolCall={bashTool()} />);
    expect(screen.getByText("Terminal")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("bun test")).toBeInTheDocument();
  });

  it("expands on click and persists the open state", () => {
    render(<ToolCallBlock toolCall={bashTool()} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details" }));
    expect(getToolLayoutOpen("tool-1")).toBe(true);
    expect(screen.getByText("3 passed")).toBeInTheDocument();
  });

  it("shows diff counts on a collapsed completed edit", () => {
    render(<ToolCallBlock toolCall={editTool()} />);
    // Completed edits auto-open (the diff body is the point); collapse back
    // to assert the summary's aggregate counts.
    fireEvent.click(screen.getByRole("button", { name: "Hide details" }));
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.getByText("−1")).toBeInTheDocument();
  });

  it("does not show diff counts while the edit is still running", () => {
    render(<ToolCallBlock toolCall={editTool({ status: "in_progress" })} />);
    expect(screen.queryByText("+2")).not.toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders the failure status word with a copyable tooltip", () => {
    render(
      <ToolCallBlock
        toolCall={bashTool({ status: "failed", rawOutput: "boom: exit 1" })}
      />
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("ToolGroupRow", () => {
  beforeEach(() => {
    toolLayoutOpenState.clear();
  });

  it("renders a grouped summary for multiple explored tools", () => {
    render(
      <ToolGroupRow
        phase="explore"
        tools={[
          bashTool({ id: "a", kind: "read", command: "", rawOutput: "x" }),
          bashTool({ id: "b", kind: "search", command: "", rawOutput: "y" }),
        ]}
        autoCollapse={false}
      />
    );
    expect(screen.getByText("Explored 2 tools")).toBeInTheDocument();
  });

  it("auto-collapses when the run settles and the answer exists", () => {
    const { rerender } = render(
      <ToolGroupRow
        phase="run"
        tools={[bashTool({ status: "in_progress" })]}
        autoCollapse={false}
      />
    );
    // While live the group auto-opens.
    expect(getToolLayoutOpen("group:tool-1")).toBe(true);

    rerender(
      <ToolGroupRow
        phase="run"
        tools={[bashTool({ status: "completed" })]}
        autoCollapse
      />
    );
    expect(getToolLayoutOpen("group:tool-1")).toBe(false);
  });
});
